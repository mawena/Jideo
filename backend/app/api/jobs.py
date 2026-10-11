"""Routes /api/jobs : création, suivi, annulation, relance, suppression, résultat."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.media import clamp_time
from app.errors import Conflict, ModelsMissing, NotFound, UserError
from app.jobs.serialize import job_to_public

router = APIRouter(prefix="/api/jobs")
PRIORITY = {"preview": 10, "photo": 0, "video": 0}


class Trim(BaseModel):
    start: float = Field(0.0, ge=0)
    end: float | None = Field(None, gt=0)


class JobCreate(BaseModel):
    type: Literal["photo", "preview", "video"]
    source_face_id: str
    target_media_id: str
    target_face_ids: list[str] | Literal["all"] = "all"
    enhance: bool | None = None
    watermark: bool = True
    similarity_threshold: float = Field(0.35, ge=0.0, le=1.0)
    t: float = Field(0.0, ge=0)
    trim: Trim | None = None
    downscale_720p: bool = False


def get_job_or_404(request: Request, job_id: str) -> dict:
    job = request.app.state.db.get_job(job_id)
    if job is None:
        raise NotFound("Tâche introuvable")
    return job


def validate(body: JobCreate, request: Request) -> dict:
    state = request.app.state
    db = state.db
    if not state.engines.ready():
        raise ModelsMissing("Modèles absents : lancez ./jideo install")
    media = db.get_media(body.target_media_id)
    if media is None:
        raise NotFound("Média cible introuvable")
    if db.get_face(body.source_face_id) is None:
        raise NotFound("Visage source introuvable")
    expected = "photo" if body.type == "photo" else "video"
    if media["kind"] != expected:
        raise UserError("Ce traitement attend une photo" if expected == "photo" else "Ce traitement attend une vidéo")
    if body.target_face_ids != "all":
        if not body.target_face_ids:
            raise UserError("Choisissez au moins un visage cible")
        for face_id in body.target_face_ids:
            face = db.get_face(face_id)
            if face is None or face["media_id"] != media["id"]:
                raise UserError("Visage cible inconnu pour ce média")

    params = body.model_dump(exclude={"type"})
    params["enhance"] = (body.type == "photo") if body.enhance is None else body.enhance
    if body.type == "preview":
        params["t"] = clamp_time(media, body.t)
    if body.type == "video":
        duration = media["duration"] or 0.0
        start = body.trim.start if body.trim else 0.0
        end = min(body.trim.end if body.trim and body.trim.end else duration, duration)
        if end - start <= 0:
            raise UserError("Le segment choisi est vide")
        limit = state.settings.max_video_seconds
        if end - start > limit:
            raise UserError(
                f"La durée à traiter ({end - start:.0f} s) dépasse la limite de {limit} s : "
                "choisissez un extrait plus court"
            )
        params["trim"] = {"start": start, "end": end}
    return params


def enqueue(request: Request, job_type: str, params: dict) -> dict:
    state = request.app.state
    job = state.db.insert_job(type=job_type, params=params, priority=PRIORITY[job_type])
    public = job_to_public(job)
    state.bus.publish({"type": "queued", "job": public})
    state.worker.wake()
    return public


@router.post("", status_code=201)
def create_job(body: JobCreate, request: Request) -> dict:
    return enqueue(request, body.type, validate(body, request))


@router.get("")
def list_jobs(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict:
    return {"items": [job_to_public(j) for j in request.app.state.db.list_jobs(limit, offset)]}


@router.get("/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    return job_to_public(get_job_or_404(request, job_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict:
    get_job_or_404(request, job_id)
    if not request.app.state.worker.cancel(job_id):
        raise Conflict("Cette tâche est déjà terminée")
    return job_to_public(get_job_or_404(request, job_id))


@router.post("/{job_id}/retry", status_code=201)
def retry_job(job_id: str, request: Request) -> dict:
    job = get_job_or_404(request, job_id)
    if job["status"] not in ("failed", "cancelled"):
        raise Conflict("Seule une tâche en échec ou annulée peut être relancée")
    return enqueue(request, job["type"], job["params"])


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, request: Request) -> Response:
    state = request.app.state
    job = get_job_or_404(request, job_id)
    if job["status"] in ("queued", "running"):
        raise Conflict("Annulez la tâche avant de la supprimer")
    state.storage.delete(job["result_path"])
    state.db.delete_job(job_id)
    return Response(status_code=204)


@router.get("/{job_id}/result")
def job_result(job_id: str, request: Request) -> FileResponse:
    job = get_job_or_404(request, job_id)
    path = job["result_path"]
    if job["status"] != "done" or not path or not Path(path).exists():
        raise NotFound("Aucun résultat pour cette tâche")
    return FileResponse(path, filename=f"jideo-{job_id[:8]}{Path(path).suffix}")
