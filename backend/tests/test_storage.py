import io

import pytest

from app.errors import FileTooLarge


def test_creates_directories(storage):
    for directory in (storage.uploads, storage.results, storage.tmp, storage.models):
        assert directory.is_dir()


def test_save_stream_writes_atomically(storage):
    dest = storage.upload_path("abc", ".png")
    assert storage.save_stream(io.BytesIO(b"x" * 10), dest, max_bytes=100) == 10
    assert dest.read_bytes() == b"x" * 10
    assert not list(storage.uploads.glob("*.part"))


def test_save_stream_rejects_oversized(storage):
    dest = storage.upload_path("abc", ".png")
    with pytest.raises(FileTooLarge):
        storage.save_stream(io.BytesIO(b"x" * 101), dest, max_bytes=100)
    assert not dest.exists()
    assert not list(storage.uploads.glob("*.part"))


def test_delete_ignores_paths_outside_data(storage, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("garder")
    storage.delete(outside, None)
    assert outside.exists()
    inside = storage.results / "r.jpg"
    inside.write_text("x")
    storage.delete(str(inside))
    assert not inside.exists()


def test_job_tmp_lifecycle(storage):
    directory = storage.job_tmp_dir("j1")
    (directory / "f").write_text("x")
    storage.clear_job_tmp("j1")
    assert not directory.exists()
    storage.job_tmp_dir("j2")
    storage.clear_tmp()
    assert list(storage.tmp.iterdir()) == []
