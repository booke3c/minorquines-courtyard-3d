"""Alternative display backends for boards without the Pimoroni Display HAT Mini.

Both classes expose the subset of the ``displayhatmini.DisplayHATMini`` API the
controller uses: ``BUTTON_A/B/X/Y`` constants, ``read_button``,
``on_button_pressed``, ``set_backlight``, ``set_led``, and ``display``.

Selection happens in ``ImageGenCamController._setup_display`` via:

- ``IMAGEGENCAM_HEADLESS=1`` -> :class:`HeadlessDisplay` (no screen at all)
- ``IMAGEGENCAM_DISPLAY=whisplay`` -> :class:`WhisplayDisplay` (PiSugar
  Whisplay HAT: 240x280 ST7789 LCD, one button, RGB LED)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

SHUTTER_EVENT_DIR = Path("/tmp/imagegencam-shutter-events")


class HeadlessDisplay:
    """No-op display so the app can run with only the phone web UI."""

    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24

    def __init__(self, buffer: Image.Image, backlight_pwm: bool = True) -> None:
        self.buffer = buffer

    def read_button(self, pin) -> bool:
        return False

    def on_button_pressed(self, callback) -> None:
        pass

    def set_backlight(self, value: float) -> None:
        pass

    def set_led(self, r: float, g: float, b: float) -> None:
        pass

    def display(self) -> None:
        pass


class WhisplayDisplay(HeadlessDisplay):
    """PiSugar Whisplay HAT backend.

    Mirrors the controller's 320x240 landscape buffer onto the 240x280
    portrait LCD (rotate, scale to width, center-crop). The single physical
    button triggers the shutter through the existing external shutter-event
    directory, so the controller needs no extra button wiring; the RGB LED
    and backlight map straight through.
    """

    def __init__(self, buffer: Image.Image, backlight_pwm: bool = True) -> None:
        super().__init__(buffer)
        whisplay_dir = Path(os.environ.get("WHISPLAY_DIR", "~/Whisplay")).expanduser()
        for sub in ("runtime", "Driver", ""):
            candidate = whisplay_dir / sub
            if candidate.is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        try:
            from whisplay import WhisplayBoard
        except ImportError:
            from WhisPlay import WhisplayBoard  # older driver layout

        self.rotation = int(os.environ.get("WHISPLAY_ROTATION", "270"))
        self.board = WhisplayBoard()
        self.board.on_button_press(self._on_button_press)
        self._last_button_event_at = 0.0
        try:
            import numpy  # noqa: F401

            self._numpy = numpy
        except ImportError:
            self._numpy = None
            logger.warning("numpy not available; LCD mirroring will be slow")

    def _on_button_press(self) -> None:
        now = time.monotonic()
        if now - self._last_button_event_at < 0.2:
            return
        self._last_button_event_at = now
        try:
            SHUTTER_EVENT_DIR.mkdir(parents=True, exist_ok=True)
            event_path = SHUTTER_EVENT_DIR / f"{time.time_ns()}-whisplay"
            event_path.write_text("shutter\n", encoding="utf-8")
        except OSError:
            logger.exception("Failed to queue Whisplay shutter event")

    def set_backlight(self, value: float) -> None:
        self.board.set_backlight(max(0, min(100, int(value * 100))))

    def set_led(self, r: float, g: float, b: float) -> None:
        self.board.set_rgb(int(r * 255), int(g * 255), int(b * 255))

    def _to_rgb565(self, image: Image.Image) -> bytes:
        if self._numpy is not None:
            arr = self._numpy.asarray(image, dtype=self._numpy.uint16)
            value = ((arr[..., 0] & 0xF8) << 8) | ((arr[..., 1] & 0xFC) << 3) | (arr[..., 2] >> 3)
            return value.astype(">u2").tobytes()
        out = bytearray()
        for r, g, b in image.getdata():
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out.append((v >> 8) & 0xFF)
            out.append(v & 0xFF)
        return bytes(out)

    def display(self) -> None:
        width = self.board.LCD_WIDTH
        height = self.board.LCD_HEIGHT
        frame = self.buffer.convert("RGB")
        if self.rotation:
            frame = frame.rotate(self.rotation, expand=True)
        scale = max(width / frame.width, height / frame.height)
        frame = frame.resize(
            (max(1, round(frame.width * scale)), max(1, round(frame.height * scale))),
            Image.BILINEAR,
        )
        left = (frame.width - width) // 2
        top = (frame.height - height) // 2
        frame = frame.crop((left, top, left + width, top + height))
        self.board.draw_image(0, 0, width, height, self._to_rgb565(frame))
