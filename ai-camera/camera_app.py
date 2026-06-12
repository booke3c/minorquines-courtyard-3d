#!/usr/bin/env python3
"""One-button AI camera for the PiSugar Whisplay HAT.

Press the button: the Pi camera (IMX708 / CAM109) takes a photo, one of
three prompt groups in prompts.json is picked at random, the photo plus
prompt is sent to OpenAI gpt-image-1 (images/edits), and the generated
image is shown on the 240x280 LCD. Hold the button for 3 seconds to shut
the Pi down safely.

LED states: green = ready, white = capturing, purple breathing =
generating, cyan = done, red = error.
"""

import base64
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- config


def _load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


_load_env_file("/etc/ai-camera.env")
_load_env_file(os.path.join(APP_DIR, ".env"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = os.environ.get("IMAGE_SIZE", "1024x1024")
IMAGE_QUALITY = os.environ.get("IMAGE_QUALITY", "medium")
INPUT_FIDELITY = os.environ.get("INPUT_FIDELITY", "")  # "high" keeps faces/details
GENERATE_TIMEOUT_SEC = int(os.environ.get("GENERATE_TIMEOUT_SEC", "300"))
PROMPTS_FILE = os.environ.get("PROMPTS_FILE", os.path.join(APP_DIR, "prompts.json"))
GALLERY_DIR = os.path.expanduser(os.environ.get("GALLERY_DIR", "~/ai-camera-gallery"))
WHISPLAY_DIR = os.path.expanduser(os.environ.get("WHISPLAY_DIR", "~/Whisplay"))
CAMERA_CMD = os.environ.get(
    "CAMERA_CMD",
    "rpicam-still -n -t 1500 --width 2304 --height 1296 --autofocus-on-capture -o {output}",
)
SHUTDOWN_HOLD_SEC = float(os.environ.get("SHUTDOWN_HOLD_SEC", "3"))

# -------------------------------------------------------- whisplay driver

for sub in ("runtime", "Driver", ""):
    path = os.path.join(WHISPLAY_DIR, sub)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

try:
    from whisplay_client import create_whisplay_hardware

    def _open_board():
        return create_whisplay_hardware(
            app_id="ai-camera",
            display_name="AI Camera",
            icon="CAM",
            launch_command=f"python3 {os.path.abspath(__file__)}",
            launch_cwd=APP_DIR,
        )
except ImportError:
    try:
        from whisplay import WhisplayBoard
    except ImportError:
        from WhisPlay import WhisplayBoard  # older driver layout

    def _open_board():
        return WhisplayBoard()


# ----------------------------------------------------------------- fonts

_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size):
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ------------------------------------------------------------ image utils


def to_rgb565(image):
    """Convert a PIL image to the big-endian RGB565 bytes the LCD expects."""
    rgb = image.convert("RGB")
    try:
        import numpy as np

        arr = np.asarray(rgb, dtype=np.uint16)
        value = ((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
        return value.astype(">u2").tobytes()
    except ImportError:
        out = bytearray()
        for r, g, b in rgb.getdata():
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out.append((v >> 8) & 0xFF)
            out.append(v & 0xFF)
        return bytes(out)


def cover_crop(image, width, height):
    """Scale to fill width x height, cropping the overflow (like CSS cover)."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


# ------------------------------------------------------------------- app


class AICamera:
    IDLE, BUSY, RESULT = "idle", "busy", "result"

    def __init__(self):
        self.board = _open_board()
        self.width = self.board.LCD_WIDTH
        self.height = self.board.LCD_HEIGHT
        self.state = self.IDLE
        self.lock = threading.Lock()
        self.press_time = None
        self.font_big = _load_font(30)
        self.font = _load_font(20)
        self.font_small = _load_font(15)
        with open(PROMPTS_FILE, encoding="utf-8") as f:
            self.prompts = json.load(f)
        if not self.prompts:
            raise RuntimeError(f"no prompts found in {PROMPTS_FILE}")
        os.makedirs(GALLERY_DIR, exist_ok=True)
        self.board.set_backlight(80)
        self.board.on_button_press(self._on_press)
        self.board.on_button_release(self._on_release)

    # ---------------------------------------------------------- display

    def show_image(self, image):
        self.board.draw_image(0, 0, self.width, self.height, to_rgb565(cover_crop(image, self.width, self.height)))

    def show_text(self, lines, bg=(12, 16, 26), fg=(235, 235, 235), accent=None):
        img = Image.new("RGB", (self.width, self.height), bg)
        draw = ImageDraw.Draw(img)
        fonts = {"big": self.font_big, "normal": self.font, "small": self.font_small}
        heights = []
        for text, style in lines:
            box = draw.textbbox((0, 0), text, font=fonts[style])
            heights.append(box[3] - box[1] + 10)
        y = (self.height - sum(heights)) // 2
        for (text, style), h in zip(lines, heights):
            font = fonts[style]
            box = draw.textbbox((0, 0), text, font=font)
            x = (self.width - (box[2] - box[0])) // 2
            color = accent if (accent and style == "big") else fg
            draw.text((x, y), text, font=font, fill=color)
            y += h
        self.show_image(img)

    def led(self, r, g, b):
        try:
            self.board.set_rgb(r, g, b)
        except Exception:
            pass

    # ----------------------------------------------------------- button

    def _on_press(self):
        self.press_time = time.monotonic()

    def _on_release(self):
        pressed = self.press_time
        self.press_time = None
        if pressed is None:
            return
        if time.monotonic() - pressed >= SHUTDOWN_HOLD_SEC:
            self._shutdown()
            return
        with self.lock:
            if self.state == self.BUSY:
                return
            self.state = self.BUSY
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _shutdown(self):
        self.led(255, 60, 0)
        self.show_text([("Shutting down", "big"), ("bye!", "normal")])
        time.sleep(1)
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)

    # --------------------------------------------------------- pipeline

    def _run_pipeline(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shot_dir = os.path.join(GALLERY_DIR, stamp)
        os.makedirs(shot_dir, exist_ok=True)
        try:
            photo = self._capture(os.path.join(shot_dir, "photo.jpg"))
            self.show_image(photo)
            time.sleep(1.2)

            choice = random.choice(self.prompts)
            with open(os.path.join(shot_dir, "prompt.txt"), "w", encoding="utf-8") as f:
                f.write(f"{choice['name']} ({choice.get('label', '')})\n\n{choice['prompt']}\n")

            stop_anim = threading.Event()
            anim = threading.Thread(target=self._generating_anim, args=(stop_anim, choice), daemon=True)
            anim.start()
            try:
                result = self._generate(photo, choice["prompt"])
            finally:
                stop_anim.set()
                anim.join(timeout=2)

            result.save(os.path.join(shot_dir, "result.png"))
            self.led(0, 200, 200)
            self.show_image(result)
            self.state = self.RESULT
            print(f"[ok] {stamp} {choice['name']} -> {shot_dir}")
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            self.led(255, 0, 0)
            self.show_text(
                [("Error", "big"), (str(exc)[:60], "small"), ("press to retry", "small")],
                bg=(40, 8, 8),
            )
            self.state = self.IDLE
            time.sleep(2)
            self.led(0, 80, 0)

    def _capture(self, output):
        self.led(255, 255, 255)
        self.show_text([("SMILE", "big"), ("capturing...", "small")], accent=(255, 220, 80))
        cmd = CAMERA_CMD.format(output=output)
        proc = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not os.path.exists(output):
            raise RuntimeError(f"camera failed: {proc.stderr.strip()[-80:] or 'no output file'}")
        return Image.open(output).convert("RGB")

    def _generating_anim(self, stop, choice):
        start = time.monotonic()
        while not stop.is_set():
            phase = (time.monotonic() * 1.5) % 2
            level = int(120 * (phase if phase <= 1 else 2 - phase)) + 40
            self.led(level, 0, level)
            elapsed = int(time.monotonic() - start)
            self.show_text(
                [
                    (choice["name"], "big"),
                    (choice.get("label", ""), "small"),
                    ("", "small"),
                    ("generating" + "." * (elapsed % 4), "normal"),
                    (f"{elapsed}s", "small"),
                ],
                bg=(20, 10, 30),
                accent=(220, 140, 255),
            )
            if stop.wait(0.5):
                break

    def _generate(self, photo, prompt):
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        # Upload a 1024px square crop instead of the full-res photo: gpt-image-1
        # works on the square anyway and Pi Zero uploads are slow.
        upload = cover_crop(photo, 1024, 1024)
        buf = io.BytesIO()
        upload.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        data = {
            "model": IMAGE_MODEL,
            "prompt": prompt,
            "size": IMAGE_SIZE,
            "quality": IMAGE_QUALITY,
            "n": "1",
        }
        if INPUT_FIDELITY:
            data["input_fidelity"] = INPUT_FIDELITY
        resp = requests.post(
            f"{OPENAI_BASE_URL}/images/edits",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            data=data,
            files={"image": ("photo.jpg", buf, "image/jpeg")},
            timeout=GENERATE_TIMEOUT_SEC,
        )
        if resp.status_code != 200:
            try:
                message = resp.json()["error"]["message"]
            except Exception:
                message = resp.text[:120]
            raise RuntimeError(f"API {resp.status_code}: {message}")
        b64 = resp.json()["data"][0]["b64_json"]
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

    # --------------------------------------------------------------- run

    def run(self):
        self.led(0, 80, 0)
        self.show_text(
            [("AI Camera", "big"), ("", "small"), ("press: shoot", "normal"), ("hold 3s: off", "small")],
            accent=(120, 255, 160),
        )
        print("ready - press the button")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.led(0, 0, 0)
            if hasattr(self.board, "cleanup"):
                self.board.cleanup()


if __name__ == "__main__":
    AICamera().run()
