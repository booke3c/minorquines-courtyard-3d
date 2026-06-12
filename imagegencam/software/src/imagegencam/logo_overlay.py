"""Post-generation brand logo overlay.

Prompt-generated logos drift between shots; compositing a real transparent
PNG after generation keeps the exhibition output consistent. Drop the logo
at ``data/assets/quickjet-logo.png`` and it is applied to every generated
image. Tune with:

- ``LOGO_OVERLAY_ENABLED`` (default ``1``; only acts when the file exists)
- ``LOGO_OVERLAY_POSITION`` (``bottom-right`` default, or ``bottom-center``)
- ``LOGO_OVERLAY_WIDTH_RATIO`` (logo width as a fraction of image width,
  default ``0.22``)
- ``LOGO_OVERLAY_MARGIN_RATIO`` (margin as a fraction of image width,
  default ``0.035``)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

LOGO_RELATIVE_PATH = Path("data") / "assets" / "quickjet-logo.png"


def overlay_enabled() -> bool:
    return os.environ.get("LOGO_OVERLAY_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def apply_logo_overlay(image_path: Path, project_root: Path) -> bool:
    """Composite the brand logo onto ``image_path`` in place.

    Returns True when an overlay was applied. Missing logo file or disabled
    flag is a silent no-op; unexpected errors are logged but never break the
    generation pipeline.
    """
    if not overlay_enabled():
        return False
    logo_path = project_root / LOGO_RELATIVE_PATH
    if not logo_path.is_file():
        return False

    try:
        width_ratio = float(os.environ.get("LOGO_OVERLAY_WIDTH_RATIO", "0.22"))
        margin_ratio = float(os.environ.get("LOGO_OVERLAY_MARGIN_RATIO", "0.035"))
        position = os.environ.get("LOGO_OVERLAY_POSITION", "bottom-right").strip().lower()

        image = Image.open(image_path)
        image_format = image.format or "JPEG"
        base = image.convert("RGBA")
        logo = Image.open(logo_path).convert("RGBA")

        logo_width = max(1, int(base.width * width_ratio))
        logo_height = max(1, round(logo.height * logo_width / logo.width))
        logo = logo.resize((logo_width, logo_height), Image.LANCZOS)

        margin = int(base.width * margin_ratio)
        if position == "bottom-center":
            x = (base.width - logo_width) // 2
        else:
            x = base.width - logo_width - margin
        y = base.height - logo_height - margin

        base.alpha_composite(logo, (max(0, x), max(0, y)))
        if image_format.upper() == "JPEG":
            base.convert("RGB").save(image_path, format="JPEG", quality=90)
        else:
            base.save(image_path, format=image_format)
        return True
    except Exception:
        logger.exception("Logo overlay failed for %s", image_path)
        return False
