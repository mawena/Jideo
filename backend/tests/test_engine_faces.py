import numpy as np
import pytest

from app.engine.detector import similarity

pytestmark = pytest.mark.slow


def test_detects_every_face_sorted_left_to_right(detector, group_img):
    faces = detector.detect(group_img)
    assert len(faces) >= 5
    xs = [f.bbox[0] for f in faces]
    assert xs == sorted(xs)
    for face in faces:
        assert face.kps.shape == (5, 2)
        assert face.embedding.shape == (512,)
        assert abs(float(np.linalg.norm(face.embedding)) - 1.0) < 1e-3


def test_blank_image_has_no_face(detector):
    assert detector.detect(np.zeros((480, 640, 3), np.uint8)) == []


def test_swap_puts_source_identity_on_target(detector, swapper, group_img, source_img):
    source = detector.detect(source_img)[0]
    target = detector.detect(group_img)[0]
    before = similarity(target.embedding, source.embedding)

    out = swapper.swap(group_img, target, source.embedding)

    assert out.shape == group_img.shape
    swapped = min(
        detector.detect(out),
        key=lambda f: abs(f.bbox[0] - target.bbox[0]) + abs(f.bbox[1] - target.bbox[1]),
    )
    assert similarity(swapped.embedding, source.embedding) > before + 0.2
