import numpy as np


def add_media(db, **kw):
    fields = dict(kind="photo", original_name="a.png", path="/data/uploads/a.png", width=10, height=20)
    fields.update(kw)
    return db.insert_media(**fields)


def test_media_roundtrip(db):
    media = add_media(db)
    assert db.get_media(media["id"])["width"] == 10
    db.delete_media(media["id"])
    assert db.get_media(media["id"]) is None


def test_face_embedding_roundtrip_and_cascade(db):
    media = add_media(db)
    embedding = np.arange(512, dtype=np.float32)
    face = db.insert_face(media_id=media["id"], index=0, t=1.5, bbox=(1, 2, 3, 4), score=0.9, embedding=embedding)
    got = db.get_face(face["id"])
    assert np.array_equal(got["embedding"], embedding)
    assert got["bbox"] == [1, 2, 3, 4] and got["idx"] == 0 and got["t"] == 1.5
    db.delete_media(media["id"])
    assert db.get_face(face["id"]) is None


def test_claim_respects_priority_then_age(db):
    first = db.insert_job(type="video", params={})
    second = db.insert_job(type="video", params={})
    preview = db.insert_job(type="preview", params={}, priority=10)
    assert db.claim_next_job()["id"] == preview["id"]
    assert db.claim_next_job()["id"] == first["id"]
    assert db.get_job(first["id"])["status"] == "running"
    assert db.get_job(first["id"])["started_at"] is not None
    assert db.claim_next_job()["id"] == second["id"]
    assert db.claim_next_job() is None


def test_update_job_serializes_json_and_paths(db, tmp_path):
    job = db.insert_job(type="photo", params={"a": 1})
    db.update_job(job["id"], status="done", stats={"faces": 2}, result_path=tmp_path / "r.jpg", progress=1.0)
    got = db.get_job(job["id"])
    assert got["params"] == {"a": 1}
    assert got["stats"] == {"faces": 2}
    assert got["result_path"] == str(tmp_path / "r.jpg")
    assert got["progress"] == 1.0


def test_cancel_queued_job_only_when_queued(db):
    job = db.insert_job(type="photo", params={})
    assert db.cancel_queued_job(job["id"])
    assert db.get_job(job["id"])["status"] == "cancelled"
    assert not db.cancel_queued_job(job["id"])


def test_mark_interrupted_jobs(db):
    job = db.insert_job(type="video", params={})
    db.claim_next_job()
    assert db.mark_interrupted_jobs() == 1
    got = db.get_job(job["id"])
    assert got["status"] == "failed"
    assert "redémarrage" in got["message"]


def test_list_jobs_newest_first(db):
    a = db.insert_job(type="photo", params={})
    b = db.insert_job(type="photo", params={})
    assert [j["id"] for j in db.list_jobs()] == [b["id"], a["id"]]
    db.delete_job(b["id"])
    assert [j["id"] for j in db.list_jobs()] == [a["id"]]
