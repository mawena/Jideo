import pytest

from tests.fakes import FakeEngineHolder, encode_image


def upload(client, name, data):
    return client.post("/api/media", files={"file": (name, data, "application/octet-stream")}).json()


def faces(client, media, t=0.0):
    return client.post(f"/api/media/{media['id']}/faces", params={"t": t}).json()["faces"]


def photo_body(media, found, **kw):
    return {"type": "photo", "source_face_id": found[0]["id"], "target_media_id": media["id"],
            "target_face_ids": [found[1]["id"]], **kw}


@pytest.fixture
def photo_ready(make_client):
    client = make_client()
    media = upload(client, "a.png", encode_image())
    return client, media, faces(client, media)


@pytest.fixture
def video_ready(make_client, sample_video):
    def _make(**overrides):
        client = make_client(**overrides)
        media = upload(client, "clip.mp4", sample_video.read_bytes())
        return client, media, faces(client, media, t=0.5)
    return _make


def test_photo_job_runs_and_serves_result(photo_ready):
    client, media, found = photo_ready
    response = client.post("/api/jobs", json=photo_body(media, found))
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "queued" and job["params"]["enhance"] is True
    assert client.app.state.worker.run_once()
    done = client.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "done"
    result = client.get(done["result_url"])
    assert result.status_code == 200 and len(result.content) > 0


def test_job_requires_models(make_client):
    holder = FakeEngineHolder()
    client = make_client(engines=holder)
    media = upload(client, "a.png", encode_image())
    found = faces(client, media)
    holder._ready = False
    assert client.post("/api/jobs", json=photo_body(media, found)).status_code == 503


def test_photo_job_rejects_video_target(video_ready):
    client, media, found = video_ready()
    response = client.post("/api/jobs", json=photo_body(media, found))
    assert response.status_code == 422


def test_target_face_must_belong_to_target_media(make_client):
    client = make_client()
    first = upload(client, "a.png", encode_image())
    second = upload(client, "b.png", encode_image())
    found_first, found_second = faces(client, first), faces(client, second)
    body = photo_body(second, found_first)  # visage cible pris sur l'autre image
    assert client.post("/api/jobs", json=body).status_code == 422
    assert client.post("/api/jobs", json=photo_body(second, found_second)).status_code == 201


def test_video_duration_limit_and_trim(video_ready):
    client, media, found = video_ready(max_video_seconds=1)
    body = {"type": "video", "source_face_id": found[0]["id"], "target_media_id": media["id"]}
    too_long = client.post("/api/jobs", json=body)
    assert too_long.status_code == 422 and "limite" in too_long.json()["detail"]
    ok = client.post("/api/jobs", json={**body, "trim": {"start": 0.5, "end": 1.2}})
    assert ok.status_code == 201
    params = ok.json()["params"]
    assert params["trim"] == {"start": 0.5, "end": 1.2}
    assert params["enhance"] is False


def test_empty_trim_is_rejected(video_ready):
    client, media, found = video_ready()
    body = {"type": "video", "source_face_id": found[0]["id"], "target_media_id": media["id"],
            "trim": {"start": 1.9, "end": 1.0}}
    assert client.post("/api/jobs", json=body).status_code == 422


def test_preview_has_priority(video_ready):
    client, media, found = video_ready()
    base = {"source_face_id": found[0]["id"], "target_media_id": media["id"]}
    client.post("/api/jobs", json={**base, "type": "video"})
    preview = client.post("/api/jobs", json={**base, "type": "preview", "t": 99}).json()
    assert preview["params"]["t"] < 2.0
    assert client.app.state.db.claim_next_job()["id"] == preview["id"]


def test_cancel_and_retry(photo_ready):
    client, media, found = photo_ready
    job = client.post("/api/jobs", json=photo_body(media, found)).json()
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409
    retried = client.post(f"/api/jobs/{job['id']}/retry")
    assert retried.status_code == 201
    assert retried.json()["id"] != job["id"]
    assert retried.json()["params"] == job["params"]
    assert client.post(f"/api/jobs/{retried.json()['id']}/retry").status_code == 409


def test_delete_job(photo_ready):
    client, media, found = photo_ready
    job = client.post("/api/jobs", json=photo_body(media, found)).json()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409  # encore en file
    client.app.state.worker.run_once()
    result_path = client.app.state.db.get_job(job["id"])["result_path"]
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert not __import__("pathlib").Path(result_path).exists()


def test_list_jobs(photo_ready):
    client, media, found = photo_ready
    for _ in range(2):
        client.post("/api/jobs", json=photo_body(media, found))
    assert len(client.get("/api/jobs").json()["items"]) == 2


def test_result_404_before_done(photo_ready):
    client, media, found = photo_ready
    job = client.post("/api/jobs", json=photo_body(media, found)).json()
    assert client.get(f"/api/jobs/{job['id']}/result").status_code == 404
