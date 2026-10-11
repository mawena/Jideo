import shutil

import cv2
import numpy as np
import pytest

from app.errors import UserError
from app.jobs.handlers import build_handlers
from app.jobs.worker import JobContext
from tests.fakes import FakeEngine, FakeEngineHolder, FakePipeline, encode_image, unit


def make_ctx(db, storage, job_type, params):
    job = db.insert_job(type=job_type, params=params)
    progress = []
    ctx = JobContext(job, storage.job_tmp_dir(job["id"]), lambda d, t, f=None: progress.append((d, t)), lambda: False)
    return ctx, progress


def params_for(source, media, **overrides):
    params = {
        "source_face_id": source["id"], "target_media_id": media["id"], "target_face_ids": "all",
        "enhance": False, "watermark": False, "similarity_threshold": 0.35, "t": 0.0,
        "trim": None, "downscale_720p": False,
    }
    params.update(overrides)
    return params


@pytest.fixture
def photo(db, storage):
    path = storage.upload_path("m1", ".png")
    path.write_bytes(encode_image(64, 48, ".png"))
    media = db.insert_media(kind="photo", original_name="t.png", path=path, width=64, height=48, media_id="m1")
    source = db.insert_face(media_id="m1", index=0, t=0, bbox=(0, 0, 10, 10), score=0.9, embedding=unit(1))
    target = db.insert_face(media_id="m1", index=1, t=0, bbox=(20, 0, 30, 10), score=0.9, embedding=unit(2))
    return media, source, target


@pytest.fixture
def video(db, storage, sample_video):
    path = storage.upload_path("v1", ".mp4")
    shutil.copy(sample_video, path)
    media = db.insert_media(kind="video", original_name="v.mp4", path=path, width=320, height=240,
                            duration=2.0, fps=10.0, has_audio=True, media_id="v1")
    source = db.insert_face(media_id="v1", index=0, t=0, bbox=(0, 0, 10, 10), score=0.9, embedding=unit(1))
    return media, source


def test_photo_handler_writes_result(db, storage, settings, photo):
    media, source, target = photo
    engines = FakeEngineHolder()
    handlers = build_handlers(db, storage, engines, settings)
    ctx, progress = make_ctx(db, storage, "photo", params_for(source, media, target_face_ids=[target["id"]]))

    result = handlers["photo"](ctx)

    assert result.result_path.suffix == ".png"
    assert cv2.imread(str(result.result_path)) is not None
    assert result.stats == {"faces_swapped": 1}
    call = engines.engine.pipeline.calls[0]
    assert np.array_equal(call["source"], source["embedding"])
    assert len(call["targets"]) == 1 and np.array_equal(call["targets"][0], target["embedding"])
    assert progress == [(1, 1)]


def test_photo_handler_fails_when_no_face_matched(db, storage, settings, photo):
    media, source, _ = photo
    engines = FakeEngineHolder(engine=FakeEngine(pipeline=FakePipeline(swapped=0)))
    ctx, _ = make_ctx(db, storage, "photo", params_for(source, media))
    with pytest.raises(UserError, match="Aucun des visages"):
        build_handlers(db, storage, engines, settings)["photo"](ctx)


def test_handler_fails_cleanly_when_target_media_was_deleted(db, storage, settings, photo):
    media, source, _ = photo
    ctx, _ = make_ctx(db, storage, "photo", params_for(source, media))
    db.delete_media(media["id"])
    with pytest.raises(UserError, match="introuvable"):
        build_handlers(db, storage, FakeEngineHolder(), settings)["photo"](ctx)


def test_preview_handler_uses_video_frame(db, storage, settings, video):
    media, source = video
    ctx, _ = make_ctx(db, storage, "preview", params_for(source, media, t=1.0))
    result = build_handlers(db, storage, FakeEngineHolder(), settings)["preview"](ctx)
    assert result.result_path.suffix == ".jpg"
    assert cv2.imread(str(result.result_path)).shape == (240, 320, 3)


def test_video_handler_reports_low_face_ratio(db, storage, settings, video):
    media, source = video
    engines = FakeEngineHolder(engine=FakeEngine(pipeline=FakePipeline(swapped=0)))
    ctx, progress = make_ctx(db, storage, "video", params_for(source, media, trim={"start": 0.0, "end": 1.0}))
    result = build_handlers(db, storage, engines, settings)["video"](ctx)
    assert result.result_path.exists()
    assert result.stats["frames"] == pytest.approx(10, abs=1)
    assert result.stats["face_ratio"] == 0
    assert "0 %" in result.message
    assert progress[-1][0] == progress[-1][1]


def test_video_handler_refuses_when_disk_is_low(db, storage, settings, video, monkeypatch):
    media, source = video
    monkeypatch.setattr(storage, "free_bytes", lambda: 10)
    ctx, _ = make_ctx(db, storage, "video", params_for(source, media))
    with pytest.raises(UserError, match="Espace disque"):
        build_handlers(db, storage, FakeEngineHolder(), settings)["video"](ctx)
