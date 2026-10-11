"""Swap photo en ligne de commande, pour le débogage.

python -m app.engine.cli --source a.jpg --target b.jpg --out c.jpg [--no-enhance] [--no-watermark]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2

from app.engine import Engine
from app.engine.watermark import save_image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.engine.cli")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument("--no-watermark", action="store_true")
    args = parser.parse_args(argv)

    engine = Engine.load(Path(os.environ.get("JIDEO_DATA_DIR", "data")) / "models")
    source_faces = engine.detector.detect(cv2.imread(str(args.source)))
    if not source_faces:
        print("✗ Aucun visage dans l'image source", file=sys.stderr)
        return 1
    result = engine.pipeline.process(
        cv2.imread(str(args.target)), source_faces[0].embedding, None,
        enhance=not args.no_enhance, watermark=not args.no_watermark, threshold=0.35,
    )
    save_image(result.image, args.out)
    print(f"✓ {result.swapped} visage(s) remplacé(s) → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
