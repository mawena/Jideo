"""Détection des visages et embeddings d'identité (InsightFace buffalo_l)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class DetectedFace:
    bbox: tuple[float, float, float, float]
    score: float
    kps: np.ndarray        # (5, 2) float32 : yeux, nez, coins de la bouche
    embedding: np.ndarray  # (512,) float32, normalisé L2


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


class FaceDetector:
    def __init__(self, models_dir: Path, det_size: tuple[int, int] = (640, 640)) -> None:
        from insightface.app import FaceAnalysis

        self._app = FaceAnalysis(
            name="buffalo_l",
            root=str(models_dir),
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],
        )
        self._app.prepare(ctx_id=-1, det_size=det_size)

    def detect(self, img: np.ndarray) -> list[DetectedFace]:
        faces = [
            DetectedFace(
                bbox=tuple(float(v) for v in f.bbox),
                score=float(f.det_score),
                kps=np.asarray(f.kps, dtype=np.float32),
                embedding=np.asarray(f.normed_embedding, dtype=np.float32),
            )
            for f in self._app.get(img)
        ]
        faces.sort(key=lambda f: (f.bbox[0], f.bbox[1]))
        return faces
