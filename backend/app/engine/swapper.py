"""Remplacement d'un visage (inswapper_128)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.engine.detector import DetectedFace


class FaceSwapper:
    def __init__(self, model_path: Path) -> None:
        from insightface.model_zoo import get_model

        self._model = get_model(str(model_path), providers=["CPUExecutionProvider"])

    def swap(self, img: np.ndarray, target: DetectedFace, source_embedding: np.ndarray) -> np.ndarray:
        # inswapper n'utilise que target.kps (alignement) et source.normed_embedding (identité).
        return self._model.get(
            img,
            SimpleNamespace(kps=target.kps),
            SimpleNamespace(normed_embedding=source_embedding),
            paste_back=True,
        )
