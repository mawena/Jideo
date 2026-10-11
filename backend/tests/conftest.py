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
    import cv2
    from insightface.data import get_image

    # L'image est un recadrage 112x112 serré sur le visage : sans marge, le détecteur ne le trouve pas.
    img = get_image("Tom_Hanks_54745")
    return cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(0, 0, 0))
