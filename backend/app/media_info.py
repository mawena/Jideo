"""Inspection des fichiers envoyés : le contenu fait foi, pas l'extension."""
from __future__ import annotations

from pathlib import Path

import cv2

from app.engine.video import VideoError, make_thumbnail, probe
from app.errors import UnsupportedMedia


def inspect_photo(path: Path, max_side: int) -> dict:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)  # applique l'orientation EXIF
    if img is None:
        raise UnsupportedMedia("Image illisible ou corrompue")
    height, width = img.shape[:2]
    if max(width, height) > max_side:
        ratio = max_side / max(width, height)
        width, height = round(width * ratio), round(height * ratio)
        cv2.imwrite(str(path), cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA))
    return {"width": width, "height": height}


def inspect_video(path: Path, thumbnail: Path) -> dict:
    try:
        info = probe(path)
        make_thumbnail(path, thumbnail)
    except VideoError as exc:
        raise UnsupportedMedia(f"Vidéo illisible ou corrompue : {exc.message}") from exc
    return {
        "width": info.width, "height": info.height, "duration": info.duration,
        "fps": info.fps, "has_audio": info.has_audio,
    }
