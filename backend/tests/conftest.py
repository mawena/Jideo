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
