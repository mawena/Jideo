import numpy as np
import pytest

pytestmark = pytest.mark.slow


def test_enhance_changes_face_region_only(models_dir, detector, group_img):
    from app.engine.enhancer import FaceEnhancer

    enhancer = FaceEnhancer(models_dir / "gfpgan_1.4.onnx")
    face = detector.detect(group_img)[0]
    out = enhancer.enhance(group_img, face)

    assert out.shape == group_img.shape and out.dtype == np.uint8
    x1, y1, x2, y2 = (int(v) for v in face.bbox)
    assert not np.array_equal(out[y1:y2, x1:x2], group_img[y1:y2, x1:x2])
    far = (slice(0, 10), slice(-10, None))  # coin haut-droit, loin du visage le plus à gauche
    assert np.array_equal(out[far], group_img[far])
