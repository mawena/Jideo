import numpy as np
import pytest
from PIL import Image

from app.engine.watermark import AI_NOTICE, add_visible_watermark, save_image


def gray(w=800, h=600):
    return np.full((h, w, 3), 128, np.uint8)


def test_visible_watermark_only_touches_bottom_right():
    img = gray()
    out = add_visible_watermark(img)
    assert out.shape == img.shape
    assert np.array_equal(out[:300, :400], img[:300, :400])
    assert not np.array_equal(out[-60:, -200:], img[-60:, -200:])
    assert np.array_equal(img, gray())  # l'original n'est pas modifié


@pytest.mark.parametrize("ext", [".jpg", ".webp"])
def test_save_image_writes_exif_notice(tmp_path, ext):
    path = tmp_path / f"out{ext}"
    save_image(gray(64, 48), path)
    with Image.open(path) as im:
        assert im.size == (64, 48)
        assert im.getexif().get(0x010E) == AI_NOTICE


def test_save_image_writes_png_text_notice(tmp_path):
    path = tmp_path / "out.png"
    save_image(gray(64, 48), path)
    with Image.open(path) as im:
        assert im.text["Description"] == AI_NOTICE
