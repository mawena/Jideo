"""Traitements exécutés par le worker : photo, aperçu (une image de vidéo), vidéo."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.engine.video import extract_frame, process_video
from app.engine.watermark import save_image
from app.errors import UserError
from app.jobs.worker import Handler, JobContext, JobResult


def build_handlers(db, storage, engines, settings) -> dict[str, Handler]:
    def source_embedding(params: dict) -> np.ndarray:
        face = db.get_face(params["source_face_id"])
        if face is None:
            raise UserError("Visage source introuvable (média supprimé ?)")
        return face["embedding"]

    def target_embeddings(params: dict) -> list[np.ndarray] | None:
        if params["target_face_ids"] == "all":
            return None
        embeddings = []
        for face_id in params["target_face_ids"]:
            face = db.get_face(face_id)
            if face is None:
                raise UserError("Visage cible introuvable (média supprimé ?)")
            embeddings.append(face["embedding"])
        return embeddings

    def target_media(params: dict) -> dict:
        media = db.get_media(params["target_media_id"])
        if media is None or not Path(media["path"]).exists():
            raise UserError("Média cible introuvable (supprimé ?)")
        return media

    def swap_image(img: np.ndarray, params: dict, pad_fallback: bool):
        src = source_embedding(params)
        targets = target_embeddings(params)
        return engines.get().pipeline.process(
            img, src, targets, enhance=params["enhance"], watermark=params["watermark"],
            threshold=params["similarity_threshold"], pad_fallback=pad_fallback,
        )

    def photo(ctx: JobContext) -> JobResult:
        media = target_media(ctx.params)
        img = cv2.imread(media["path"], cv2.IMREAD_COLOR)
        if img is None:
            raise UserError("Image cible illisible")
        result = swap_image(img, ctx.params, pad_fallback=True)  # visages choisis via /faces (avec repli)
        if result.swapped == 0:
            raise UserError("Aucun des visages choisis n'a été retrouvé dans l'image cible")
        dest = storage.result_path(ctx.job["id"], Path(media["path"]).suffix.lower())
        save_image(result.image, dest)
        ctx.report_progress(1, 1)
        return JobResult(dest, {"faces_swapped": result.swapped})

    def preview(ctx: JobContext) -> JobResult:
        media = target_media(ctx.params)
        result = swap_image(extract_frame(Path(media["path"]), float(ctx.params.get("t", 0.0))), ctx.params,
                            pad_fallback=False)
        dest = storage.result_path(ctx.job["id"], ".jpg")
        save_image(result.image, dest)
        ctx.report_progress(1, 1)
        message = None if result.swapped else "Aucun visage correspondant sur cette image"
        return JobResult(dest, {"faces_swapped": result.swapped}, message)

    def video(ctx: JobContext) -> JobResult:
        if storage.free_bytes() < settings.min_free_gb * 1024**3:
            raise UserError(f"Espace disque insuffisant : moins de {settings.min_free_gb:g} Go libres")
        params = ctx.params
        media = target_media(params)
        src = source_embedding(params)
        targets = target_embeddings(params)
        pipeline = engines.get().pipeline

        def frame_fn(frame: np.ndarray) -> tuple[np.ndarray, bool]:
            r = pipeline.process(
                frame, src, targets, enhance=params["enhance"], watermark=params["watermark"],
                threshold=params["similarity_threshold"], pad_fallback=False,
            )
            return r.image, r.swapped > 0

        trim = params.get("trim") or {}
        dest = storage.result_path(ctx.job["id"], ".mp4")
        stats = process_video(
            Path(media["path"]), dest, frame_fn,
            start=trim.get("start", 0.0), end=trim.get("end"),
            downscale_720p=params.get("downscale_720p", False), tmp_dir=ctx.tmp_dir,
            on_progress=ctx.report_progress, should_cancel=ctx.should_cancel,
        )
        ratio = round(100 * stats.frames_with_face / stats.frames_total)
        message = f"Visage cible trouvé sur {ratio} % des images seulement" if ratio < 50 else None
        return JobResult(
            dest, {"frames": stats.frames_total, "frames_with_face": stats.frames_with_face, "face_ratio": ratio},
            message,
        )

    return {"photo": photo, "preview": preview, "video": video}
