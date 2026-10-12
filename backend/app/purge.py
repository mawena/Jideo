"""Suppression automatique des médias et résultats trop anciens."""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("jideo.purge")


def purge(db, storage, retention_days: int, *, now: float | None = None) -> dict:
    if retention_days <= 0:
        return {"jobs": 0, "media": 0}
    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    jobs = media = 0
    for job in db.jobs_created_before(cutoff):
        storage.delete(job["result_path"])
        db.delete_job(job["id"])
        jobs += 1
    for item in db.media_created_before(cutoff):
        if db.media_in_use(item["id"]):
            continue
        storage.delete(item["path"], item["thumbnail_path"])
        db.delete_media(item["id"])
        media += 1
    return {"jobs": jobs, "media": media}


class PurgeThread:
    def __init__(self, db, storage, retention_days: int, interval_s: float = 6 * 3600) -> None:
        self.db = db
        self.storage = storage
        self.retention_days = retention_days
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="jideo-purge", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                removed = purge(self.db, self.storage, self.retention_days)
                if removed["jobs"] or removed["media"]:
                    log.info("Purge : %(jobs)s tâche(s), %(media)s média(s) supprimés", removed)
            except Exception:
                log.exception("Échec de la purge")
            self._stop.wait(self.interval_s)
