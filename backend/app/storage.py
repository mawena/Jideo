"""Seul module qui lit ou écrit dans data/."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.errors import FileTooLarge

CHUNK = 1024 * 1024


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir).resolve()
        self.uploads = self.root / "uploads"
        self.results = self.root / "results"
        self.tmp = self.root / "tmp"
        self.models = self.root / "models"
        for directory in (self.uploads, self.results, self.tmp, self.models):
            directory.mkdir(parents=True, exist_ok=True)

    def upload_path(self, media_id: str, ext: str) -> Path:
        return self.uploads / f"{media_id}{ext}"

    def thumbnail_path(self, media_id: str) -> Path:
        return self.uploads / f"{media_id}.thumb.jpg"

    def result_path(self, job_id: str, ext: str) -> Path:
        return self.results / f"{job_id}{ext}"

    def job_tmp_dir(self, job_id: str) -> Path:
        directory = self.tmp / job_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def clear_job_tmp(self, job_id: str) -> None:
        shutil.rmtree(self.tmp / job_id, ignore_errors=True)

    def clear_tmp(self) -> None:
        for child in self.tmp.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def save_stream(self, src: BinaryIO, dest: Path, max_bytes: int) -> int:
        part = dest.with_name(dest.name + ".part")
        written = 0
        try:
            with part.open("wb") as out:
                while chunk := src.read(CHUNK):
                    written += len(chunk)
                    if written > max_bytes:
                        raise FileTooLarge(
                            f"Fichier trop volumineux (maximum {max_bytes // (1024 * 1024)} Mo)"
                        )
                    out.write(chunk)
            part.replace(dest)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return written

    def delete(self, *paths: Path | str | None) -> None:
        for raw in paths:
            if not raw:
                continue
            path = Path(raw).resolve()
            if path.is_relative_to(self.root):
                path.unlink(missing_ok=True)

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free
