import numpy as np
import pytest

from app.engine import EngineHolder
from app.engine.pipeline import FaceSwapPipeline, match_faces
from app.errors import ModelsMissing
from tests.fakes import FakeDetector, make_face, unit


class RecordingSwapper:
    def __init__(self):
        self.targets = []

    def swap(self, img, target, source_embedding):
        self.targets.append(target)
        return img + 1


class RecordingEnhancer:
    def __init__(self):
        self.faces = []

    def enhance(self, img, face):
        self.faces.append(face)
        return img


def test_match_faces_all_when_no_targets():
    faces = [make_face(0, 1), make_face(50, 2)]
    assert match_faces(faces, None, 0.35) == faces


def test_match_faces_by_similarity():
    f1, f2 = make_face(0, 1), make_face(50, 2)
    assert match_faces([f1, f2], [f2.embedding], 0.35) == [f2]


def test_pipeline_swaps_matching_faces_then_enhances():
    f1, f2 = make_face(0, 1), make_face(50, 2)
    swapper, enhancer = RecordingSwapper(), RecordingEnhancer()
    pipeline = FaceSwapPipeline(FakeDetector([f1, f2]), swapper, enhancer)
    result = pipeline.process(
        np.zeros((100, 100, 3), np.uint8), unit(9), [f1.embedding], enhance=True, watermark=False, threshold=0.35
    )
    assert result.swapped == 1
    assert swapper.targets == [f1] and enhancer.faces == [f1]
    assert int(result.image[0, 0, 0]) == 1


def test_pipeline_without_enhance_adds_watermark():
    swapper, enhancer = RecordingSwapper(), RecordingEnhancer()
    pipeline = FaceSwapPipeline(FakeDetector([make_face(0, 1), make_face(50, 2)]), swapper, enhancer)
    result = pipeline.process(
        np.zeros((600, 800, 3), np.uint8), unit(9), None, enhance=False, watermark=True, threshold=0.35
    )
    assert result.swapped == 2 and enhancer.faces == []
    assert int(result.image[0, 0, 0]) == 2
    assert (result.image != 2).any()


def test_holder_reports_missing_models(tmp_path):
    holder = EngineHolder(tmp_path, loader=lambda d: pytest.fail("ne doit pas charger"))
    assert not holder.ready()
    with pytest.raises(ModelsMissing):
        holder.get()


def test_holder_loads_once(tmp_path, monkeypatch):
    monkeypatch.setattr("app.engine.missing_models", lambda d: [])
    calls = []
    holder = EngineHolder(tmp_path, loader=lambda d: calls.append(d) or "moteur")
    assert holder.get() == "moteur" and holder.get() == "moteur"
    assert len(calls) == 1


@pytest.mark.slow
def test_real_pipeline_swaps_every_face(models_dir, detector, group_img, source_img):
    from app.engine import Engine

    engine = Engine.load(models_dir)
    source = detector.detect(source_img)[0]
    result = engine.pipeline.process(
        group_img, source.embedding, None, enhance=True, watermark=True, threshold=0.35
    )
    assert result.swapped == len(detector.detect(group_img))
    assert result.image.shape == group_img.shape


@pytest.mark.parametrize("flag", [True, False])
def test_pipeline_forwards_pad_fallback_to_the_detector(flag):
    detector = FakeDetector([make_face(0, 1)])
    pipeline = FaceSwapPipeline(detector, RecordingSwapper())
    pipeline.process(
        np.zeros((100, 100, 3), np.uint8), unit(9), None, enhance=False, watermark=False, threshold=0.35,
        pad_fallback=flag,
    )
    assert detector.pad_fallbacks == [flag]
