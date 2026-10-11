"""Restauration du visage après swap (GFPGAN 1.4, ONNX, entrée 512×512)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.engine.detector import DetectedFace

SIZE = 512
# Gabarit FFHQ 512 de facexlib : yeux, nez, coins de la bouche.
FFHQ_512 = np.array(
    [[192.98138, 239.94708], [318.90277, 240.19366], [256.63416, 314.01935],
     [201.26117, 371.41043], [313.08905, 371.15118]],
    dtype=np.float32,
)


def _paste_back(img: np.ndarray, crop: np.ndarray, matrix: np.ndarray, blend: float) -> np.ndarray:
    h, w = img.shape[:2]
    inverse = cv2.invertAffineTransform(matrix)
    warped = cv2.warpAffine(crop, inverse, (w, h), borderMode=cv2.BORDER_REPLICATE)
    mask = np.zeros((SIZE, SIZE), np.float32)
    margin = SIZE // 10
    mask[margin:-margin, margin:-margin] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=SIZE / 20)
    mask = cv2.warpAffine(mask, inverse, (w, h))[..., None] * blend
    out = img.astype(np.float32) * (1 - mask) + warped.astype(np.float32) * mask
    return out.clip(0, 255).astype(np.uint8)


class FaceEnhancer:
    def __init__(self, model_path: Path, blend: float = 0.8) -> None:
        import onnxruntime as ort

        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name
        self._blend = blend

    def enhance(self, img: np.ndarray, face: DetectedFace) -> np.ndarray:
        matrix, _ = cv2.estimateAffinePartial2D(face.kps, FFHQ_512, method=cv2.LMEDS)
        crop = cv2.warpAffine(img, matrix, (SIZE, SIZE), borderMode=cv2.BORDER_REPLICATE)
        x = crop[:, :, ::-1].astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        y = self._session.run(None, {self._input: x})[0][0]
        y = (np.clip(y, -1, 1) + 1) / 2
        restored = (y.transpose(1, 2, 0)[:, :, ::-1] * 255).round().astype(np.uint8)
        return _paste_back(img, restored, matrix, self._blend)
