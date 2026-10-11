import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture
def storage(settings):
    from app.storage import Storage

    return Storage(settings.data_dir)


@pytest.fixture
def db(settings):
    from app.db import Database

    database = Database(settings.db_path)
    yield database
    database.close()


@pytest.fixture(scope="session")
def models_dir():
    import os
    from pathlib import Path

    from app.engine.models import missing_models

    directory = Path(os.environ.get("JIDEO_DATA_DIR", "data")) / "models"
    missing = missing_models(directory)
    if missing:
        pytest.skip(f"modèles absents : {', '.join(missing)} (lancez ./jideo install)")
    return directory


@pytest.fixture(scope="session")
def detector(models_dir):
    from app.engine.detector import FaceDetector

    return FaceDetector(models_dir)


@pytest.fixture(scope="session")
def swapper(models_dir):
    from app.engine.swapper import FaceSwapper

    return FaceSwapper(models_dir / "inswapper_128.onnx")


@pytest.fixture(scope="session")
def group_img():
    from insightface.data import get_image

    return get_image("t1")


@pytest.fixture(scope="session")
def source_img():
    from insightface.data import get_image

    return get_image("Tom_Hanks_54745")


@pytest.fixture(scope="session")
def make_video(tmp_path_factory):
    import subprocess

    directory = tmp_path_factory.mktemp("videos")

    def _make(name, *args):
        out = directory / name
        if not out.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(out)], check=True)
        return out

    return _make


@pytest.fixture(scope="session")
def sample_video(make_video):
    return make_video(
        "sample.mp4",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    )
