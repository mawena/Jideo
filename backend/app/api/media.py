"""Routes /api/media : upload, lecture, détection des visages."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
from fastapi import APIRouter, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.db import new_id
from app.engine.video import extract_frame
from app.errors import NotFound, UnsupportedMedia, UserError
from app.media_info import inspect_photo, inspect_video

log = logging.getLogger("jideo.media")
router = APIRouter(prefix="/api/media")

PHOTO_EXTENSIONS = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}
VIDEO_EXTENSIONS = {".mp4": ".mp4", ".mov": ".mov", ".webm": ".webm", ".mkv": ".mkv"}


def media_to_public(media: dict) -> dict:
    return {
        "id": media["id"],
        "kind": media["kind"],
        "original_name": media["original_name"],
        "width": media["width"],
        "height": media["height"],
        "duration": media["duration"],
        "fps": media["fps"],
        "has_audio": None if media["has_audio"] is None else bool(media["has_audio"]),
        "created_at": media["created_at"],
        "url": f"/api/media/{media['id']}/file",
        "thumbnail_url": f"/api/media/{media['id']}/thumbnail" if media["thumbnail_path"] else None,
    }


def face_to_public(face: dict) -> dict:
    return {"id": face["id"], "index": face["idx"], "bbox": face["bbox"], "score": face["score"]}


def get_media_or_404(request: Request, media_id: str) -> dict:
    media = request.app.state.db.get_media(media_id)
    if media is None:
        raise NotFound("Média introuvable")
    return media


def clamp_time(media: dict, t: float) -> float:
    # Marge d'une image et demie : ffmpeg ne renvoie rien au-delà du pts de la dernière image.
    margin = max(0.05, 1.5 / (media["fps"] or 30.0))
    return min(max(0.0, t), max(0.0, (media["duration"] or 0.0) - margin))


@router.post("", status_code=201)
def upload_media(request: Request, file: UploadFile) -> dict:
    state = request.app.state
    ext = Path(file.filename or "").suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        kind, ext, limit_mb = "photo", PHOTO_EXTENSIONS[ext], state.settings.max_photo_mb
    elif ext in VIDEO_EXTENSIONS:
        kind, ext, limit_mb = "video", VIDEO_EXTENSIONS[ext], state.settings.max_video_mb
    else:
        raise UnsupportedMedia(
            f"Format non pris en charge ({ext or 'sans extension'}) : "
            "utilisez JPG, PNG, WEBP, MP4, MOV, WEBM ou MKV"
        )
    media_id = new_id()
    path = state.storage.upload_path(media_id, ext)
    state.storage.save_stream(file.file, path, limit_mb * 1024 * 1024)
    thumbnail = state.storage.thumbnail_path(media_id) if kind == "video" else None
    try:
        info = (
            inspect_photo(path, state.settings.max_photo_side) if kind == "photo"
            else inspect_video(path, thumbnail)
        )
    except Exception as exc:
        state.storage.delete(path, thumbnail)
        if isinstance(exc, UserError):
            raise
        log.exception("Analyse du fichier téléversé impossible")
        raise UnsupportedMedia("Fichier illisible ou corrompu") from exc
    media = state.db.insert_media(
        media_id=media_id, kind=kind, original_name=file.filename or path.name,
        path=path, thumbnail_path=thumbnail, **info,
    )
    return media_to_public(media)


@router.get("/{media_id}")
def get_media(media_id: str, request: Request) -> dict:
    return media_to_public(get_media_or_404(request, media_id))


@router.get("/{media_id}/file")
def media_file(media_id: str, request: Request) -> FileResponse:
    return FileResponse(get_media_or_404(request, media_id)["path"])


@router.get("/{media_id}/thumbnail")
def media_thumbnail(media_id: str, request: Request) -> FileResponse:
    media = get_media_or_404(request, media_id)
    if not media["thumbnail_path"]:
        raise NotFound("Pas de miniature pour ce média")
    return FileResponse(media["thumbnail_path"])


@router.get("/{media_id}/frame")
def media_frame(media_id: str, request: Request, t: float = 0.0) -> Response:
    media = get_media_or_404(request, media_id)
    if media["kind"] != "video":
        raise UserError("Ce média n'est pas une vidéo")
    img = extract_frame(Path(media["path"]), clamp_time(media, t))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.post("/{media_id}/faces")
def detect_faces(media_id: str, request: Request, t: float = 0.0) -> dict:
    state = request.app.state
    media = get_media_or_404(request, media_id)
    engine = state.engines.get()  # ModelsMissing → 503
    if media["kind"] == "video":
        t = clamp_time(media, t)
        img = extract_frame(Path(media["path"]), t)
    else:
        t = 0.0
        img = cv2.imread(media["path"], cv2.IMREAD_COLOR)
    if img is None:
        raise UserError("Média illisible")
    faces = engine.detector.detect(img)
    rows = [
        state.db.insert_face(media_id=media_id, index=i, t=t, bbox=f.bbox, score=f.score, embedding=f.embedding)
        for i, f in enumerate(faces)
    ]
    return {"t": t, "width": int(img.shape[1]), "height": int(img.shape[0]),
            "faces": [face_to_public(r) for r in rows]}


@router.delete("/{media_id}", status_code=204)
def delete_media(media_id: str, request: Request) -> Response:
    state = request.app.state
    media = get_media_or_404(request, media_id)
    state.storage.delete(media["path"], media["thumbnail_path"])
    state.db.delete_media(media_id)
    return Response(status_code=204)
