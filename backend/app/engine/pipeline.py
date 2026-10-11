"""Swap sur une image : détection → sélection → swap → amélioration → filigrane."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.engine.detector import DetectedFace, similarity
from app.engine.watermark import add_visible_watermark


@dataclass
class FrameResult:
    image: np.ndarray
    swapped: int


def match_faces(
    faces: list[DetectedFace], target_embeddings: list[np.ndarray] | None, threshold: float
) -> list[DetectedFace]:
    if target_embeddings is None:
        return list(faces)
    return [f for f in faces if any(similarity(f.embedding, t) >= threshold for t in target_embeddings)]


class FaceSwapPipeline:
    def __init__(self, detector, swapper, enhancer=None) -> None:
        self.detector = detector
        self.swapper = swapper
        self.enhancer = enhancer

    def process(
        self, img: np.ndarray, source_embedding: np.ndarray, target_embeddings: list[np.ndarray] | None,
        *, enhance: bool, watermark: bool, threshold: float,
    ) -> FrameResult:
        faces = match_faces(self.detector.detect(img), target_embeddings, threshold)
        out = img
        for face in faces:
            out = self.swapper.swap(out, face, source_embedding)
        if enhance and self.enhancer is not None:
            for face in faces:
                out = self.enhancer.enhance(out, face)
        if watermark:
            out = add_visible_watermark(out)
        return FrameResult(out, len(faces))
