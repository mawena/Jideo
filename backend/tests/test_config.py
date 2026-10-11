import pytest

from app.config import ConfigError, load_settings


def env(tmp_path, **extra):
    return {"JIDEO_DATA_DIR": str(tmp_path), **extra}


def test_defaults_are_local_without_auth(tmp_path):
    s = load_settings(env(tmp_path))
    assert s.bind == "127.0.0.1"
    assert not s.auth_required
    assert (s.max_photo_mb, s.max_video_mb, s.max_video_seconds, s.retention_days) == (25, 1024, 300, 30)
    assert s.max_photo_side == 4096
    assert s.db_path == tmp_path.resolve() / "jideo.sqlite"
    assert len(s.secret) >= 32


def test_network_bind_requires_password(tmp_path):
    with pytest.raises(ConfigError, match="JIDEO_PASSWORD"):
        load_settings(env(tmp_path, JIDEO_BIND="0.0.0.0"))


def test_network_bind_requires_long_secret(tmp_path):
    with pytest.raises(ConfigError, match="JIDEO_SECRET"):
        load_settings(env(tmp_path, JIDEO_BIND="0.0.0.0", JIDEO_PASSWORD="pw", JIDEO_SECRET="court"))


def test_network_bind_with_password_enables_auth(tmp_path):
    s = load_settings(env(tmp_path, JIDEO_BIND="0.0.0.0", JIDEO_PASSWORD="pw", JIDEO_SECRET="x" * 32))
    assert s.auth_required


def test_invalid_integer_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="JIDEO_MAX_PHOTO_MB"):
        load_settings(env(tmp_path, JIDEO_MAX_PHOTO_MB="beaucoup"))
