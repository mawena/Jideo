import threading
import time

import pytest

from app.errors import Cancelled, UserError
from app.jobs.worker import JobResult, Worker


class RecordingBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def make_worker(db, storage, handlers):
    bus = RecordingBus()
    return Worker(db, storage, bus, handlers), bus


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_run_once_without_jobs(db, storage):
    worker, _ = make_worker(db, storage, {})
    assert worker.run_once() is False


def test_successful_job(db, storage):
    def handler(ctx):
        (ctx.tmp_dir / "brouillon").write_text("x")
        dest = storage.result_path(ctx.job["id"], ".txt")
        dest.write_text("ok")
        ctx.report_progress(5, 10, 2.0)
        return JobResult(dest, {"n": 1}, "note")

    worker, bus = make_worker(db, storage, {"photo": handler})
    job = db.insert_job(type="photo", params={})
    assert worker.run_once()
    got = db.get_job(job["id"])
    assert got["status"] == "done" and got["progress"] == 1.0
    assert got["stats"] == {"n": 1} and got["message"] == "note"
    assert [e["type"] for e in bus.events] == ["started", "progress", "done"]
    assert bus.events[1]["progress"] == 0.5
    assert bus.events[1]["eta_s"] == pytest.approx(2.5)
    assert bus.events[-1]["job"]["result_url"] == f"/api/jobs/{job['id']}/result"
    assert not (storage.tmp / job["id"]).exists()


def test_user_error_marks_failed_with_message(db, storage):
    def handler(ctx):
        raise UserError("Aucun visage")

    worker, bus = make_worker(db, storage, {"photo": handler})
    job = db.insert_job(type="photo", params={})
    worker.run_once()
    got = db.get_job(job["id"])
    assert got["status"] == "failed" and got["message"] == "Aucun visage"
    assert bus.events[-1]["type"] == "failed"


def test_unexpected_error_marks_failed(db, storage):
    def handler(ctx):
        raise RuntimeError("boum")

    worker, _ = make_worker(db, storage, {"photo": handler})
    job = db.insert_job(type="photo", params={})
    worker.run_once()
    got = db.get_job(job["id"])
    assert got["status"] == "failed"
    assert got["message"] == "Erreur interne (voir les journaux du serveur)"
    assert "boum" not in got["message"]


def test_unserializable_stats_fail_instead_of_staying_running(db, storage):
    worker, bus = make_worker(db, storage, {"photo": lambda ctx: JobResult(None, {"x": object()})})
    job = db.insert_job(type="photo", params={})
    worker.run_once()
    got = db.get_job(job["id"])
    assert got["status"] == "failed" and got["finished_at"] is not None
    assert bus.events[-1]["type"] == "failed"


def test_unknown_type_fails(db, storage):
    worker, _ = make_worker(db, storage, {})
    job = db.insert_job(type="mystere", params={})
    worker.run_once()
    assert db.get_job(job["id"])["status"] == "failed"


def test_cancel_queued_job(db, storage):
    worker, bus = make_worker(db, storage, {"photo": lambda ctx: pytest.fail("ne doit pas tourner")})
    job = db.insert_job(type="photo", params={})
    assert worker.cancel(job["id"])
    assert db.get_job(job["id"])["status"] == "cancelled"
    assert worker.run_once() is False
    assert [e["type"] for e in bus.events] == ["cancelled"]


def test_cancel_running_job(db, storage):
    started = threading.Event()

    def handler(ctx):
        started.set()
        while not ctx.should_cancel():
            time.sleep(0.01)
        raise Cancelled()

    worker, bus = make_worker(db, storage, {"video": handler})
    job = db.insert_job(type="video", params={})
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    assert started.wait(2)
    assert worker.cancel(job["id"])
    thread.join(2)
    assert not thread.is_alive()
    assert db.get_job(job["id"])["status"] == "cancelled"
    assert bus.events[-1]["type"] == "cancelled"


def test_cancel_running_job_that_ignores_the_flag(db, storage):
    started, release = threading.Event(), threading.Event()
    dest = storage.result_path("x", ".txt")

    def handler(ctx):
        dest.write_text("résultat")
        started.set()
        release.wait(2)
        return JobResult(dest)

    worker, bus = make_worker(db, storage, {"photo": handler})
    job = db.insert_job(type="photo", params={})
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    assert started.wait(2)
    assert worker.cancel(job["id"])
    release.set()
    thread.join(2)
    assert not thread.is_alive()
    got = db.get_job(job["id"])
    assert got["status"] == "cancelled" and got["finished_at"] is not None
    assert not dest.exists()
    assert bus.events[-1]["type"] == "cancelled" and bus.events[-1]["job"]["result_url"] is None


def test_cancel_unknown_job_returns_false(db, storage):
    worker, _ = make_worker(db, storage, {})
    assert worker.cancel("inconnu") is False
    assert worker._cancel == set()


def test_cancel_finished_job_returns_false(db, storage):
    worker, _ = make_worker(db, storage, {"photo": lambda ctx: JobResult(None)})
    job = db.insert_job(type="photo", params={})
    worker.run_once()
    assert worker.cancel(job["id"]) is False


def test_background_thread_processes_queue(db, storage):
    worker, _ = make_worker(db, storage, {"photo": lambda ctx: JobResult(None)})
    worker.start()
    try:
        job = db.insert_job(type="photo", params={})
        worker.wake()
        assert wait_for(lambda: db.get_job(job["id"])["status"] == "done")
    finally:
        worker.stop()
