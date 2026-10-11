"""Worker unique : exécute les tâches une par une, dans un thread dédié."""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.errors import Cancelled, UserError
from app.jobs.serialize import job_to_public

log = logging.getLogger("jideo.worker")

INTERNAL_ERROR = "Erreur interne (voir les journaux du serveur)"


@dataclass
class JobResult:
    result_path: Path | None
    stats: dict = field(default_factory=dict)
    message: str | None = None


class JobContext:
    def __init__(self, job: dict, tmp_dir: Path, report: Callable, cancelled: Callable[[], bool]) -> None:
        self.job = job
        self.params = job["params"]
        self.tmp_dir = tmp_dir
        self._report = report
        self._cancelled = cancelled

    def report_progress(self, done: int, total: int, fps: float | None = None) -> None:
        self._report(done, total, fps)

    def should_cancel(self) -> bool:
        return self._cancelled()


Handler = Callable[[JobContext], JobResult]


class Worker:
    def __init__(self, db, storage, bus, handlers: dict[str, Handler]) -> None:
        self.db = db
        self.storage = storage
        self.bus = bus
        self.handlers = handlers
        self._cancel: set[str] = set()
        self._current: str | None = None
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="jideo-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        # La tâche en cours n'est pas annulée : au redémarrage elle sera marquée « interrompue ».
        self._stop.set()
        self._wakeup.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if not self._thread.is_alive():
                self._thread = None

    def wake(self) -> None:
        self._wakeup.set()

    def cancel(self, job_id: str) -> bool:
        if self.db.cancel_queued_job(job_id):
            self._publish("cancelled", job_id)
            return True
        with self._lock:
            if self._current == job_id:
                self._cancel.add(job_id)
                return True
        return False

    def run_once(self) -> bool:
        job = self.db.claim_next_job()
        if job is None:
            return False
        self._execute(job)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                log.exception("Erreur du worker")
                worked = False
            if not worked:
                self._wakeup.wait(0.5)
                self._wakeup.clear()

    def _execute(self, job: dict) -> None:
        job_id = job["id"]
        with self._lock:
            self._current = job_id
        try:
            status = self._run(job)
        except Exception:
            log.exception("Tâche %s en échec", job_id)
            status = self._finish(job_id, "failed", message=INTERNAL_ERROR)
        finally:
            with self._lock:
                self._cancel.discard(job_id)
                self._current = None
            try:
                self.storage.clear_job_tmp(job_id)
            except Exception:
                log.exception("Nettoyage impossible pour la tâche %s", job_id)
        self._publish(status, job_id)

    def _run(self, job: dict) -> str:
        job_id = job["id"]
        self._publish("started", job_id)
        tmp_dir = self.storage.job_tmp_dir(job_id)
        started = time.monotonic()

        def report(done: int, total: int, fps: float | None) -> None:
            progress = min(1.0, done / total) if total else 0.0
            if fps is None:
                elapsed = time.monotonic() - started
                fps = done / elapsed if elapsed > 0 and done else None
            eta = (total - done) / fps if fps else None
            self.db.update_job(job_id, progress=progress)
            self.bus.publish({
                "type": "progress", "job_id": job_id, "progress": progress, "fps": fps,
                "eta_s": eta, "frames_done": done, "frames_total": total,
            })

        def cancelled() -> bool:
            with self._lock:
                return job_id in self._cancel

        handler = self.handlers.get(job["type"])
        try:
            if handler is None:
                raise UserError(f"Type de tâche inconnu : {job['type']}")
            result = handler(JobContext(job, tmp_dir, report, cancelled))
        except Cancelled:
            return self._finish(job_id, "cancelled")
        except UserError as exc:
            return self._finish(job_id, "failed", message=exc.message)
        except Exception:
            log.exception("Tâche %s en échec", job_id)
            return self._finish(job_id, "failed", message=INTERNAL_ERROR)

        # Le traitement est terminé : on tranche ici, sous verrou, pour qu'un cancel() tardif renvoie False.
        with self._lock:
            was_cancelled = job_id in self._cancel
            self._current = None
        if was_cancelled:
            self.storage.delete(result.result_path)
            return self._finish(job_id, "cancelled")
        return self._finish(
            job_id, "done", progress=1.0, result_path=result.result_path,
            stats=result.stats, message=result.message,
        )

    def _finish(self, job_id: str, status: str, **fields) -> str:
        """Écrit l'état final ; si l'écriture échoue, la tâche passe en « failed » plutôt que de rester « running »."""
        try:
            self.db.update_job(job_id, status=status, finished_at=time.time(), **fields)
            return status
        except Exception:
            log.exception("Impossible d'enregistrer l'état %s de la tâche %s", status, job_id)
        try:
            self.db.update_job(job_id, status="failed", message="Erreur interne", finished_at=time.time())
        except Exception:
            log.exception("Impossible de marquer la tâche %s en échec", job_id)
        return "failed"

    def _publish(self, event_type: str, job_id: str) -> None:
        job = self.db.get_job(job_id)
        if job is not None:
            self.bus.publish({"type": event_type, "job": job_to_public(job)})
