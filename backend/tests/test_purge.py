import time

from app.purge import purge

LATER = time.time() + 31 * 86400  # tout ce qui est créé maintenant a « plus de 30 jours » à cette date


def add_media(db, storage, name):
    path = storage.upload_path(name, ".png")
    path.write_bytes(b"x")
    return db.insert_media(kind="photo", original_name=f"{name}.png", path=path, width=1, height=1, media_id=name)


def test_purge_removes_old_finished_jobs_and_unused_media(db, storage):
    unused = add_media(db, storage, "libre")
    busy = add_media(db, storage, "occupe")
    done = db.insert_job(type="photo", params={"target_media_id": unused["id"]})
    result = storage.result_path(done["id"], ".png")
    result.write_bytes(b"r")
    db.update_job(done["id"], status="done", result_path=result)
    queued = db.insert_job(type="photo", params={"target_media_id": busy["id"]})

    assert purge(db, storage, 30, now=LATER) == {"jobs": 1, "media": 1}

    assert db.get_job(done["id"]) is None and not result.exists()
    assert db.get_job(queued["id"]) is not None
    assert db.get_media(unused["id"]) is None and not storage.upload_path("libre", ".png").exists()
    assert db.get_media(busy["id"]) is not None


def test_recent_items_are_kept(db, storage):
    add_media(db, storage, "recent")
    assert purge(db, storage, 30) == {"jobs": 0, "media": 0}


def test_zero_retention_disables_purge(db, storage):
    add_media(db, storage, "vieux")
    assert purge(db, storage, 0, now=LATER) == {"jobs": 0, "media": 0}
