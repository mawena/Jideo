"""Configuration de Jideo, lue une fois depuis l'environnement."""
from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

LOCAL_BINDS = {"127.0.0.1", "localhost", "::1"}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    bind: str = "127.0.0.1"
    password: str | None = None
    secret: str = "jideo-local-secret-not-used-without-auth"
    max_photo_mb: int = 25
    max_video_mb: int = 1024
    max_video_seconds: int = 300
    retention_days: int = 30
    max_photo_side: int = 4096
    min_free_gb: float = 2.0

    @property
    def auth_required(self) -> bool:
        return self.bind not in LOCAL_BINDS

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jideo.sqlite"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env

    def integer(name: str, default: int) -> int:
        raw = env.get(name, "")
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} doit être un entier (reçu {raw!r})") from exc

    settings = Settings(
        data_dir=Path(env.get("JIDEO_DATA_DIR", "data")).resolve(),
        bind=env.get("JIDEO_BIND", "127.0.0.1").strip() or "127.0.0.1",
        password=env.get("JIDEO_PASSWORD") or None,
        secret=env.get("JIDEO_SECRET") or secrets.token_hex(32),
        max_photo_mb=integer("JIDEO_MAX_PHOTO_MB", 25),
        max_video_mb=integer("JIDEO_MAX_VIDEO_MB", 1024),
        max_video_seconds=integer("JIDEO_MAX_VIDEO_SECONDS", 300),
        retention_days=integer("JIDEO_RETENTION_DAYS", 30),
    )
    if settings.auth_required:
        if not settings.password:
            raise ConfigError(
                f"JIDEO_BIND={settings.bind} expose Jideo au réseau : définissez JIDEO_PASSWORD dans .env"
            )
        if len(settings.secret) < 32:
            raise ConfigError("JIDEO_SECRET doit contenir au moins 32 caractères")
    return settings
