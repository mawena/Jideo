"""Doublures du moteur IA pour tester sans les modèles."""
import cv2
import numpy as np

from app.engine.detector import DetectedFace
from app.engine.pipeline import FrameResult
from app.errors import ModelsMissing


def unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


def make_face(x: float, seed: int) -> DetectedFace:
    return DetectedFace(
        bbox=(x, 10.0, x + 40.0, 60.0), score=0.9, kps=np.zeros((5, 2), np.float32), embedding=unit(seed)
    )


def encode_image(w: int = 64, h: int = 48, ext: str = ".png") -> bytes:
    img = np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()


class FakeDetector:
    def __init__(self, faces=None):
        self.faces = faces if faces is not None else [make_face(10, 1), make_face(80, 2)]

    def detect(self, img):
        return list(self.faces)


class FakePipeline:
    def __init__(self, swapped: int = 1):
        self.swapped = swapped
        self.calls = []

    def process(self, img, source_embedding, target_embeddings, *, enhance, watermark, threshold):
        self.calls.append(
            {"source": source_embedding, "targets": target_embeddings, "enhance": enhance,
             "watermark": watermark, "threshold": threshold}
        )
        return FrameResult(255 - img, self.swapped)


class FakeEngine:
    def __init__(self, detector=None, pipeline=None):
        self.detector = detector or FakeDetector()
        self.pipeline = pipeline or FakePipeline()


class FakeEngineHolder:
    def __init__(self, engine=None, ready: bool = True):
        self.engine = engine or FakeEngine()
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    def get(self):
        if not self._ready:
            raise ModelsMissing("Modèles absents : lancez ./jideo install")
        return self.engine
