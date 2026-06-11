from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from imagegencam.logo_overlay import LOGO_RELATIVE_PATH, apply_logo_overlay


def _make_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="JPEG", quality=90)


class LogoOverlayTests(unittest.TestCase):
    def test_no_op_when_logo_asset_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            generated = project_root / "data" / "generated" / "result.jpg"
            _make_image(generated, (640, 480), (10, 10, 10))
            before = generated.read_bytes()

            self.assertFalse(apply_logo_overlay(generated, project_root))
            self.assertEqual(generated.read_bytes(), before)

    def test_applies_logo_to_bottom_right(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            logo_path = project_root / LOGO_RELATIVE_PATH
            logo_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo_path, format="PNG")

            generated = project_root / "data" / "generated" / "result.jpg"
            _make_image(generated, (640, 480), (10, 10, 10))

            self.assertTrue(apply_logo_overlay(generated, project_root))

            result = Image.open(generated).convert("RGB")
            margin = int(640 * 0.035)
            sample = result.getpixel((640 - margin - 10, 480 - margin - 10))
            self.assertGreater(sample[0], 150, f"expected red logo pixel, got {sample}")
            untouched = result.getpixel((10, 10))
            self.assertLess(untouched[0], 60, f"expected dark background, got {untouched}")


if __name__ == "__main__":
    unittest.main()
