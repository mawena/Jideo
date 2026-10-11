"""Téléchargement et vérification des modèles ONNX.

Usage : python -m app.engine.models download|check [--models-dir DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


class ModelChecksumError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    sha256: str
    required_files: tuple[str, ...]
    extract_to: str | None = None  # archive zip extraite dans models_dir/<extract_to>


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="buffalo_l",
        url="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        sha256="80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f",
        extract_to="models/buffalo_l",
        required_files=("models/buffalo_l/det_10g.onnx", "models/buffalo_l/w600k_r50.onnx"),
    ),
    ModelSpec(
        name="inswapper_128",
        url="https://huggingface.co/ezioruan/inswapper_128.onnx/resolve/main/inswapper_128.onnx",
        sha256="e4a3f08c753cb72d04e10aa0f7dbe3deebbf39567d4ead6dce08e98aa49e16af",
        required_files=("inswapper_128.onnx",),
    ),
    ModelSpec(
        name="gfpgan_1.4",
        url="https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gfpgan_1.4.onnx",
        sha256="accc4757b26bdb89b32b4d3500d4f79c9dff97c1dd7c7104bf9dcb95e3311385",
        required_files=("gfpgan_1.4.onnx",),
    ),
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def missing_models(models_dir: Path, specs: tuple[ModelSpec, ...] = MODEL_SPECS) -> list[str]:
    return [s.name for s in specs if not all((Path(models_dir) / f).is_file() for f in s.required_files)]


def _flatten(directory: Path) -> None:
    children = list(directory.iterdir())
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        for item in inner.iterdir():
            item.rename(directory / item.name)
        inner.rmdir()


def download_model(spec: ModelSpec, models_dir: Path, *, log=print) -> str:
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    part = models_dir / f"{spec.name}.download"
    log(f"↓ {spec.name} …")
    try:
        with urllib.request.urlopen(spec.url, timeout=60) as response, part.open("wb") as out:
            shutil.copyfileobj(response, out, 1024 * 1024)
        digest = sha256_of(part)
        if spec.sha256 and digest != spec.sha256:
            raise ModelChecksumError(
                f"{spec.name} : somme de contrôle invalide (attendu {spec.sha256}, obtenu {digest})"
            )
        if spec.extract_to:
            dest = models_dir / spec.extract_to
            shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True)
            with zipfile.ZipFile(part) as zf:
                zf.extractall(dest)
            _flatten(dest)
            part.unlink()
        else:
            part.replace(models_dir / spec.required_files[0])
    finally:
        part.unlink(missing_ok=True)
    log(f"✓ {spec.name} (sha256 {digest})")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.engine.models")
    parser.add_argument("command", choices=["download", "check"])
    parser.add_argument(
        "--models-dir", type=Path, default=Path(os.environ.get("JIDEO_DATA_DIR", "data")) / "models"
    )
    args = parser.parse_args(argv)
    missing = missing_models(args.models_dir, MODEL_SPECS)
    if args.command == "check":
        print("✓ Tous les modèles sont présents" if not missing else "✗ Manquants : " + ", ".join(missing))
        return 1 if missing else 0
    for spec in MODEL_SPECS:
        if spec.name in missing:
            try:
                download_model(spec, args.models_dir)
            except (ModelChecksumError, urllib.error.URLError, zipfile.BadZipFile, OSError) as exc:
                print(f"✗ {spec.name} : échec du téléchargement ({exc})", file=sys.stderr)
                return 1
        else:
            print(f"✓ {spec.name} déjà présent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
