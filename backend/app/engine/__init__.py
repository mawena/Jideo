"""Moteur IA : chargé une seule fois, à la première utilisation."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.engine.models import missing_models
from app.engine.pipeline import FaceSwapPipeline
from app.errors import ModelsMissing


@dataclass
class Engine:
    detector: object
    swapper: object
    enhancer: object
    pipeline: FaceSwapPipeline = field(init=False)

    def __post_init__(self) -> None:
        self.pipeline = FaceSwapPipeline(self.detector, self.swapper, self.enhancer)

    @classmethod
    def load(cls, models_dir: Path) -> "Engine":
        from app.engine.detector import FaceDetector
        from app.engine.enhancer import FaceEnhancer
        from app.engine.swapper import FaceSwapper

        return cls(
            FaceDetector(models_dir),
            FaceSwapper(models_dir / "inswapper_128.onnx"),
            FaceEnhancer(models_dir / "gfpgan_1.4.onnx"),
        )


class EngineHolder:
    def __init__(self, models_dir: Path, loader: Callable[[Path], Engine] | None = None) -> None:
        self.models_dir = Path(models_dir)
        self._loader = loader or Engine.load
        self._engine = None
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return self._engine is not None or not missing_models(self.models_dir)

    def get(self) -> Engine:
        with self._lock:
            if self._engine is None:
                missing = missing_models(self.models_dir)
                if missing:
                    raise ModelsMissing(f"Modèles absents ({', '.join(missing)}) : lancez ./jideo install")
                self._engine = self._loader(self.models_dir)
            return self._engine
