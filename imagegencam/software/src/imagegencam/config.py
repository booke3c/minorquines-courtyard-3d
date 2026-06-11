from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import Lock


PROMPT_TITLE_MAX_LENGTH = 22
CAMERA_USERNAME_MAX_LENGTH = 32
DEFAULT_NEW_PROMPT_TITLE = "New Prompt"
DEFAULT_NEW_PROMPT_BODY = "Describe the edit you want."
DEFAULT_PROMPT_ENTRIES = [
    {
        "id": "prompt-1",
        "title": "Sketch Souvenir",
        "body": (
            "Transform the photo into a playful rough-line sketch in the spirit of an old computer paint "
            "program, hand-drawn with bold uneven black outlines, simple flat colors, charming imperfect "
            "proportions, and a funny exhibition souvenir feeling. Keep the person recognizable and preserve "
            "the face clearly."
            "\n\nThe background should suggest QuickJet as a CNC machine tool manufacturer: CNC machine "
            "frames, spindle head assemblies, linear guide rails, ball screws, tool magazine components, "
            "control panels, neatly routed cables, and engineers assembling or calibrating machine tools. "
            "The scene should feel like a clever hand-drawn technical cartoon about building high-precision "
            "CNC equipment, not a customer machining shop."
            "\n\nAdd the QuickJet company logo as a clean branded mark. The logo should read "
            "\u201cQuickJet\u201d in a fast, elegant white italic brush-script wordmark, with a small orange "
            "accent dot above the i and a long thin speed underline sweeping under \u201cJet\u201d. Place it "
            "near the lower center or lower right as a tasteful exhibition watermark. Do not cover any face, "
            "eyes, hands, or important subject details. Keep the logo crisp and recognizable."
        ),
    },
    {
        "id": "prompt-2",
        "title": "Premium Souvenir",
        "body": (
            "Create a polished exhibition souvenir portrait based on the photo. Keep the person "
            "recognizable, friendly, and natural. Make the image feel premium, precise, and memorable, "
            "suitable for a CNC machine tool manufacturer showing advanced capability at a trade show."
            "\n\nSurround the subject with a refined machine-building environment: CNC machining centers "
            "being assembled, rigid machine frames, spindle units, linear guide rails, ball screws, "
            "automatic tool changers, control cabinets, HMI panels, servo drive components, precision "
            "alignment tools, clean cable routing, and engineers carefully inspecting and calibrating the "
            "machines. Communicate structural rigidity, high precision, reliability, careful adjustment, and "
            "craftsmanship in manufacturing CNC equipment itself."
            "\n\nDo not make it look like a general metalworking job shop or customer-side machining "
            "operation. Avoid random loose metal parts, sparks, sci-fi robots, or fantasy elements. The mood "
            "should be confident, modern, clean, and technically credible."
            "\n\nAdd the QuickJet company logo as a clean branded mark. The logo should read "
            "\u201cQuickJet\u201d in a fast, elegant white italic brush-script wordmark, with a small orange "
            "accent dot above the i and a long thin speed underline sweeping under \u201cJet\u201d. Place it "
            "near the lower center or lower right as a tasteful exhibition watermark. Do not cover any face, "
            "eyes, hands, or important subject details. Keep the logo crisp and recognizable."
        ),
    },
    {
        "id": "prompt-3",
        "title": "Craftsman Brand",
        "body": (
            "Turn the photo into a premium brand image for QuickJet, a CNC equipment manufacturer. Preserve "
            "the person\u2019s identity and facial features. The result should feel like a high-end "
            "engineering portrait: precise, calm, reliable, and crafted with pride."
            "\n\nBuild the scene around the manufacturing and calibration of CNC machine tools: cast bases, "
            "machine columns, spindle head assemblies, linear guide rails, ball screws, tool changers, "
            "enclosure panels, HMI control panels, electrical cabinets, servo systems, measuring indicators, "
            "alignment tools, and engineers performing final assembly and quality checks. Show the machine "
            "as the product being created, not merely a tool used by a customer."
            "\n\nVisual style: realistic but slightly cinematic, clean industrial lighting, sharp details, "
            "premium materials, disciplined composition, strong sense of precision and craftsmanship. Avoid "
            "exaggeration, clutter, fantasy, and generic factory imagery."
            "\n\nAdd the QuickJet company logo as a clean branded mark. The logo should read "
            "\u201cQuickJet\u201d in a fast, elegant white italic brush-script wordmark, with a small orange "
            "accent dot above the i and a long thin speed underline sweeping under \u201cJet\u201d. Place it "
            "near the lower center or lower right as a tasteful exhibition watermark. Do not cover any face, "
            "eyes, hands, or important subject details. Keep the logo crisp and recognizable."
        ),
    },
]
DEFAULT_PROMPTS = {
    entry["id"]: entry["body"] for entry in DEFAULT_PROMPT_ENTRIES
}

DEFAULT_SETTINGS = {
    "app_background_theme": "aqua",
    "camera_username": "",
    "preview_warmth": 0,
    "preview_red_gain": 100,
    "preview_green_gain": 100,
    "preview_blue_gain": 100,
}

VALID_APP_BACKGROUND_THEMES = {"aqua", "silver", "lavender", "mint", "sunset"}


def _clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, numeric))


def _default_prompt_map() -> dict[str, dict[str, str]]:
    return {
        entry["id"]: {"title": entry["title"], "body": entry["body"]}
        for entry in DEFAULT_PROMPT_ENTRIES
    }


def _normalize_magic_history_id(value: object, used_ids: set[str], fallback_index: int) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not raw:
        raw = f"magic-{fallback_index}"

    candidate = raw
    suffix = 2
    while candidate in used_ids:
        candidate = f"{raw}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _normalize_prompt_title(value: object) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        cleaned = DEFAULT_NEW_PROMPT_TITLE
    return cleaned[:PROMPT_TITLE_MAX_LENGTH].strip() or DEFAULT_NEW_PROMPT_TITLE


def _normalize_prompt_body(value: object) -> str:
    cleaned = str(value or "").strip()
    return cleaned or DEFAULT_NEW_PROMPT_BODY


def _normalize_camera_username(value: object) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"[^a-z0-9._-]+", "", cleaned)
    return cleaned[:CAMERA_USERNAME_MAX_LENGTH].strip("._-")


def _normalize_prompt_id(value: object, used_ids: set[str], fallback_index: int) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if not raw:
        raw = f"prompt-{fallback_index}"

    candidate = raw
    suffix = 2
    while candidate in used_ids:
        candidate = f"{raw}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def normalize_prompt_entries(
    prompts: object,
    *,
    ensure_defaults_when_empty: bool = True,
) -> dict[str, dict[str, str]]:
    if isinstance(prompts, dict):
        iterable = []
        for key, value in prompts.items():
            if isinstance(value, dict):
                iterable.append(
                    {
                        "id": value.get("id", key),
                        "title": value.get("title", DEFAULT_NEW_PROMPT_TITLE),
                        "body": value.get("body", DEFAULT_NEW_PROMPT_BODY),
                    }
                )
            else:
                iterable.append(
                    {
                        "id": key,
                        "title": DEFAULT_NEW_PROMPT_TITLE,
                        "body": value,
                    }
                )
    elif isinstance(prompts, list):
        iterable = [entry for entry in prompts if isinstance(entry, dict)]
    else:
        iterable = []

    cleaned: dict[str, dict[str, str]] = {}
    used_ids: set[str] = set()
    for index, entry in enumerate(iterable, start=1):
        prompt_id = _normalize_prompt_id(entry.get("id"), used_ids, index)
        cleaned[prompt_id] = {
            "title": _normalize_prompt_title(entry.get("title")),
            "body": _normalize_prompt_body(entry.get("body")),
        }

    if not cleaned and ensure_defaults_when_empty:
        return _default_prompt_map()
    return cleaned


def normalize_magic_history_entries(entries: object) -> list[dict[str, str | None]]:
    if not isinstance(entries, list):
        return []

    cleaned: list[dict[str, str | None]] = []
    used_ids: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        cleaned.append(
            {
                "id": _normalize_magic_history_id(entry.get("id"), used_ids, index),
                "created_at": str(entry.get("created_at") or "").strip(),
                "title": _normalize_prompt_title(entry.get("title")),
                "body": _normalize_prompt_body(entry.get("body")),
                "reference_capture_path": str(entry.get("reference_capture_path") or "").strip() or None,
                "promoted_prompt_id": str(entry.get("promoted_prompt_id") or "").strip() or None,
            }
        )
    return cleaned


def normalize_settings(data: dict[str, object]) -> dict[str, int | str]:
    settings: dict[str, int | str] = DEFAULT_SETTINGS.copy()

    app_background_theme = str(
        data.get("app_background_theme", settings["app_background_theme"])
    ).strip()
    if app_background_theme in VALID_APP_BACKGROUND_THEMES:
        settings["app_background_theme"] = app_background_theme

    settings["camera_username"] = _normalize_camera_username(
        data.get("camera_username", settings["camera_username"])
    )

    settings["preview_warmth"] = _clamp_int(
        data.get("preview_warmth"),
        int(DEFAULT_SETTINGS["preview_warmth"]),
        -40,
        40,
    )
    settings["preview_red_gain"] = _clamp_int(
        data.get("preview_red_gain"),
        int(DEFAULT_SETTINGS["preview_red_gain"]),
        60,
        160,
    )
    settings["preview_green_gain"] = _clamp_int(
        data.get("preview_green_gain"),
        int(DEFAULT_SETTINGS["preview_green_gain"]),
        60,
        160,
    )
    settings["preview_blue_gain"] = _clamp_int(
        data.get("preview_blue_gain"),
        int(DEFAULT_SETTINGS["preview_blue_gain"]),
        60,
        160,
    )
    return settings


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class PromptStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save_entries(DEFAULT_PROMPT_ENTRIES)

    def load_entries(self) -> dict[str, dict[str, str]]:
        with self._lock:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        return normalize_prompt_entries(data)

    def load(self) -> dict[str, str]:
        entries = self.load_entries()
        return {prompt_id: entry["body"] for prompt_id, entry in entries.items()}

    def save_entries(self, prompts: object) -> dict[str, dict[str, str]]:
        cleaned = normalize_prompt_entries(prompts)
        serializable = [
            {"id": prompt_id, "title": entry["title"], "body": entry["body"]}
            for prompt_id, entry in cleaned.items()
        ]
        with self._lock:
            self.path.write_text(
                json.dumps(serializable, indent=2) + "\n",
                encoding="utf-8",
            )
        return cleaned

    def save(self, prompts: dict[str, str]) -> dict[str, str]:
        cleaned_entries = self.save_entries(
            [
                {
                    "id": prompt_id,
                    "title": DEFAULT_NEW_PROMPT_TITLE,
                    "body": body,
                }
                for prompt_id, body in prompts.items()
            ]
        )
        return {prompt_id: entry["body"] for prompt_id, entry in cleaned_entries.items()}


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(DEFAULT_SETTINGS)

    def load(self) -> dict[str, int | str]:
        with self._lock:
            data = json.loads(self.path.read_text(encoding="utf-8"))

        return normalize_settings(data)

    def save(self, settings: dict[str, object]) -> dict[str, int | str]:
        cleaned = normalize_settings(settings)

        with self._lock:
            self.path.write_text(
                json.dumps(cleaned, indent=2) + "\n",
                encoding="utf-8",
            )
        return cleaned


class MagicHistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save_entries([])

    def load_entries(self) -> list[dict[str, str | None]]:
        with self._lock:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        return normalize_magic_history_entries(data)

    def save_entries(self, entries: object) -> list[dict[str, str | None]]:
        cleaned = normalize_magic_history_entries(entries)
        with self._lock:
            self.path.write_text(
                json.dumps(cleaned, indent=2) + "\n",
                encoding="utf-8",
            )
        return cleaned

    def add_entry(self, entry: dict[str, object]) -> dict[str, str | None]:
        entries = self.load_entries()
        entries.insert(0, dict(entry))
        cleaned = self.save_entries(entries)
        return cleaned[0]

    def mark_promoted(self, entry_id: str, prompt_id: str) -> list[dict[str, str | None]]:
        entries = self.load_entries()
        for entry in entries:
            if entry["id"] == entry_id:
                entry["promoted_prompt_id"] = prompt_id.strip() or None
                break
        return self.save_entries(entries)
