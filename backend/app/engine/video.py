"""Vidéo : lecture en flux par ffmpeg, traitement image par image, réencodage + audio d'origine.

Aucune image intermédiaire n'est écrite sur disque.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.engine.watermark import AI_NOTICE
from app.errors import Cancelled, UserError

log = logging.getLogger("jideo.video")

PROGRESS_EVERY_FRAMES = 10
PROGRESS_EVERY_SECONDS = 2.0  # publie aussi quand les images sont lentes (GFPGAN, visages nombreux)

FrameFn = Callable[[np.ndarray], tuple[np.ndarray, bool]]


class VideoError(UserError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


@dataclass(frozen=True)
class VideoStats:
    frames_total: int
    frames_with_face: int


def _run(cmd: list[str], error: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip().splitlines()[-3:]
        log.warning("%s : %s (code %s) : %s", error, cmd[0], proc.returncode, " | ".join(detail))
        raise VideoError(error)
    return proc


def _log_tails(*logs: Path) -> None:
    for path in logs:
        try:
            tail = path.read_bytes()[-2000:].decode(errors="replace").strip().splitlines()[-5:]
        except OSError:
            continue
        if tail:
            log.warning("%s : %s", path.name, " | ".join(tail))


def _rate(value: str | None) -> float:
    if not value or "/" not in value:
        return float(value or 0)
    num, den = value.split("/")
    return float(num) / float(den) if float(den) else 0.0


def _rotation(stream: dict) -> int:
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(float(side["rotation"]))
    return int(float(stream.get("tags", {}).get("rotate", 0)))


def probe(path: Path) -> VideoInfo:
    proc = _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        "Vidéo illisible",
    )
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise VideoError("Aucune piste vidéo dans ce fichier")
    width, height = int(video["width"]), int(video["height"])
    if abs(_rotation(video)) % 180 == 90:  # ffmpeg applique la rotation au décodage
        width, height = height, width
    fps = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if fps <= 0 or duration <= 0:
        raise VideoError("Vidéo illisible (durée ou cadence inconnue)")
    return VideoInfo(
        width=width, height=height, fps=fps, duration=duration,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def extract_frame(path: Path, t: float) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True,
    )
    img = cv2.imdecode(np.frombuffer(proc.stdout, np.uint8), cv2.IMREAD_COLOR) if proc.stdout else None
    if proc.returncode != 0 or img is None:
        raise VideoError(f"Impossible d'extraire une image à {t:.2f} s")
    return img


def make_thumbnail(path: Path, dest: Path, t: float = 0.0, width: int = 480) -> None:
    _run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"scale={width}:-2", str(dest)],
        "Impossible de créer la miniature",
    )


def output_size(width: int, height: int, downscale_720p: bool) -> tuple[int, int]:
    if downscale_720p and min(width, height) > 720:
        ratio = 720 / min(width, height)
        width, height = round(width * ratio), round(height * ratio)
    return width - width % 2, height - height % 2


def _mux(video: Path, src: Path, start: float, duration: float, dst: Path,
         has_audio: bool, notice: str, tmp_dir: Path) -> None:
    part = tmp_dir / "muxed.mp4"
    meta = ["-metadata", f"comment={notice}", "-movflags", "+faststart"]
    if not has_audio:
        _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-c:v", "copy", *meta, str(part)],
             "Échec de l'assemblage de la vidéo")
    else:
        base = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video),
                "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-shortest"]
        try:
            _run([*base, "-c:a", "copy", *meta, str(part)], "Copie de l'audio impossible")
        except VideoError:  # ex. Vorbis/Opus non accepté tel quel en MP4
            _run([*base, "-c:a", "aac", "-b:a", "192k", *meta, str(part)], "Échec de l'encodage audio")
    shutil.move(part, dst)


def process_video(
    src: Path, dst: Path, frame_fn: FrameFn, *, start: float = 0.0, end: float | None = None,
    downscale_720p: bool = False, tmp_dir: Path,
    on_progress: Callable[[int, int, float | None], None],
    should_cancel: Callable[[], bool], notice: str = AI_NOTICE,
) -> VideoStats:
    info = probe(src)
    start = max(0.0, start or 0.0)
    end = info.duration if end is None else min(end, info.duration)
    if end <= start:
        raise VideoError("Le segment choisi est vide")
    duration = end - start
    width, height = output_size(info.width, info.height, downscale_720p)
    total = max(1, round(duration * info.fps))
    frame_bytes = width * height * 3
    silent = tmp_dir / "video.mp4"

    decode = ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
              "-vf", f"fps={info.fps:.6f},scale={width}:{height}",
              "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    encode = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
              "-s", f"{width}x{height}", "-r", f"{info.fps:.6f}", "-i", "-",
              "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(silent)]

    with (tmp_dir / "decode.log").open("wb") as dec_log, (tmp_dir / "encode.log").open("wb") as enc_log:
        dec = enc = None
        done = matched = 0
        started = last_report = time.monotonic()
        last_done = 0
        try:
            dec = subprocess.Popen(decode, stdout=subprocess.PIPE, stderr=dec_log)
            enc = subprocess.Popen(encode, stdin=subprocess.PIPE, stderr=enc_log)
            while True:
                if should_cancel():
                    raise Cancelled()
                buf = dec.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                frame = np.frombuffer(buf, np.uint8).reshape(height, width, 3).copy()
                out, found = frame_fn(frame)
                enc.stdin.write(np.ascontiguousarray(out).tobytes())
                done += 1
                matched += int(found)
                now = time.monotonic()
                if done - last_done >= PROGRESS_EVERY_FRAMES or now - last_report >= PROGRESS_EVERY_SECONDS:
                    last_done, last_report = done, now
                    elapsed = now - started
                    on_progress(done, max(total, done), done / elapsed if elapsed > 0 else None)
            enc.stdin.close()
            if enc.wait() != 0:
                _log_tails(tmp_dir / "encode.log")
                raise VideoError("Échec de l'encodage vidéo")
            if dec.wait() != 0 or done < 0.9 * total:
                _log_tails(tmp_dir / "decode.log")
                raise VideoError("La vidéo source n'a pas pu être lue jusqu'au bout")
        except BrokenPipeError as exc:
            _log_tails(tmp_dir / "encode.log")
            raise VideoError("Échec de l'encodage vidéo") from exc
        finally:
            for proc in (dec, enc):
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait()

    if done == 0:
        raise VideoError("Aucune image n'a pu être lue dans ce segment")
    elapsed = time.monotonic() - started
    on_progress(done, done, done / elapsed if elapsed > 0 else None)
    _mux(silent, src, start, duration, dst, info.has_audio, notice, tmp_dir)
    return VideoStats(frames_total=done, frames_with_face=matched)
