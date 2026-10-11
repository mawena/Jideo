import hashlib
import zipfile

import pytest

from app.engine import models as m


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quiet(_message):
    pass


def test_all_models_have_pinned_checksums():
    for spec in m.MODEL_SPECS:
        assert len(spec.sha256) == 64, f"{spec.name} : SHA-256 non figé"


def test_missing_models_lists_absent_specs(tmp_path):
    assert set(m.missing_models(tmp_path)) == {s.name for s in m.MODEL_SPECS}


def test_download_single_file_verifies_checksum(tmp_path):
    src = tmp_path / "src.onnx"
    src.write_bytes(b"model")
    spec = m.ModelSpec(name="x", url=src.as_uri(), sha256=sha(src), required_files=("x.onnx",))
    m.download_model(spec, tmp_path / "models", log=quiet)
    assert (tmp_path / "models" / "x.onnx").read_bytes() == b"model"
    assert m.missing_models(tmp_path / "models", specs=(spec,)) == []


def test_download_rejects_bad_checksum(tmp_path):
    src = tmp_path / "src.onnx"
    src.write_bytes(b"model")
    spec = m.ModelSpec(name="x", url=src.as_uri(), sha256="0" * 64, required_files=("x.onnx",))
    with pytest.raises(m.ModelChecksumError):
        m.download_model(spec, tmp_path / "models", log=quiet)
    assert list((tmp_path / "models").iterdir()) == []


def test_download_zip_is_extracted_and_flattened(tmp_path):
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("pack/a.onnx", b"a")
        zf.writestr("pack/b.onnx", b"b")
    spec = m.ModelSpec(
        name="pack", url=archive.as_uri(), sha256=sha(archive), extract_to="models/pack",
        required_files=("models/pack/a.onnx", "models/pack/b.onnx"),
    )
    m.download_model(spec, tmp_path / "models", log=quiet)
    assert m.missing_models(tmp_path / "models", specs=(spec,)) == []
    assert not list((tmp_path / "models").glob("*.download"))


def test_main_download_reports_failure_in_french(tmp_path, monkeypatch, capsys):
    spec = m.ModelSpec(
        name="x", url=(tmp_path / "absent.onnx").as_uri(), sha256="0" * 64, required_files=("x.onnx",)
    )
    monkeypatch.setattr(m, "MODEL_SPECS", (spec,))
    assert m.main(["download", "--models-dir", str(tmp_path / "models")]) == 1
    assert "✗ x : échec du téléchargement" in capsys.readouterr().err


def test_main_check_returns_1_when_models_missing(tmp_path, capsys):
    assert m.main(["check", "--models-dir", str(tmp_path)]) == 1
    assert "Manquants" in capsys.readouterr().out
