from tests.fakes import FakeEngineHolder, encode_image


def upload(client, name, data, mime="application/octet-stream"):
    return client.post("/api/media", files={"file": (name, data, mime)})


def uploads(client):
    return list(client.app.state.storage.uploads.iterdir())


def test_upload_photo(make_client):
    client = make_client()
    response = upload(client, "Visage.PNG", encode_image(64, 48, ".png"), "image/png")
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "photo" and (body["width"], body["height"]) == (64, 48)
    assert body["thumbnail_url"] is None
    assert client.get(body["url"]).status_code == 200
    assert client.get(f"/api/media/{body['id']}").json()["id"] == body["id"]


def test_upload_rejects_unknown_extension(make_client):
    client = make_client()
    response = upload(client, "notes.txt", b"bonjour")
    assert response.status_code == 415
    assert "Format non pris en charge" in response.json()["detail"]


def test_upload_rejects_corrupted_image(make_client):
    client = make_client()
    assert upload(client, "photo.jpg", b"pas une image").status_code == 415
    assert uploads(client) == []


def test_upload_rejects_too_large(make_client):
    client = make_client(max_photo_mb=1)
    response = upload(client, "big.png", b"\0" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert "1 Mo" in response.json()["detail"]
    assert uploads(client) == []


def test_large_photo_is_downscaled(make_client):
    client = make_client(max_photo_side=100)
    body = upload(client, "grande.jpg", encode_image(300, 150, ".jpg")).json()
    assert (body["width"], body["height"]) == (100, 50)


def test_upload_video_with_thumbnail(make_client, sample_video):
    client = make_client()
    body = upload(client, "clip.MP4", sample_video.read_bytes()).json()
    assert body["kind"] == "video"
    assert body["duration"] == 2.0 or abs(body["duration"] - 2.0) < 0.1
    assert body["fps"] == 10.0 and body["has_audio"] is True
    assert client.get(body["thumbnail_url"]).status_code == 200
    frame = client.get(f"/api/media/{body['id']}/frame", params={"t": 1})
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"


def test_detect_faces_persists_embeddings(make_client):
    client = make_client()
    media = upload(client, "a.png", encode_image()).json()
    body = client.post(f"/api/media/{media['id']}/faces").json()
    assert (body["width"], body["height"], body["t"]) == (64, 48, 0.0)
    assert [f["index"] for f in body["faces"]] == [0, 1]
    stored = client.app.state.db.get_face(body["faces"][0]["id"])
    assert stored["media_id"] == media["id"] and stored["embedding"].shape == (512,)


def test_detect_faces_on_video_clamps_time(make_client, sample_video):
    client = make_client()
    media = upload(client, "clip.mp4", sample_video.read_bytes()).json()
    body = client.post(f"/api/media/{media['id']}/faces", params={"t": 99}).json()
    assert body["t"] < 2.0 and (body["width"], body["height"]) == (320, 240)


def test_detect_faces_requires_models(make_client):
    client = make_client(engines=FakeEngineHolder(ready=False))
    media = upload(client, "a.png", encode_image()).json()
    response = client.post(f"/api/media/{media['id']}/faces")
    assert response.status_code == 503
    assert "./jideo install" in response.json()["detail"]


def test_unknown_media_is_404(make_client):
    assert make_client().get("/api/media/inconnu").status_code == 404


def test_delete_media(make_client):
    client = make_client()
    media = upload(client, "a.png", encode_image()).json()
    assert client.delete(f"/api/media/{media['id']}").status_code == 204
    assert client.get(f"/api/media/{media['id']}").status_code == 404
    assert uploads(client) == []


def test_health_reports_models(make_client):
    body = make_client(engines=FakeEngineHolder(ready=False)).get("/api/health").json()
    assert body == {"status": "ok", "models_ready": False, "auth_required": False, "authenticated": True}
