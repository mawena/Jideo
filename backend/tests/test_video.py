import json
import subprocess

import numpy as np
import pytest

from app.engine.video import (
    VideoError, extract_frame, make_thumbnail, output_size, probe, process_video,
)
from app.engine.watermark import AI_NOTICE
from app.errors import Cancelled


def ffprobe_format(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)["format"]


def identity(frame):
    return frame, True


def run(src, dst, tmp_path, frame_fn=identity, **kw):
    progress = []
    kw.setdefault("should_cancel", lambda: False)
    stats = process_video(
        src, dst, frame_fn, tmp_dir=tmp_path, on_progress=lambda d, t, f: progress.append((d, t)), **kw
    )
    return stats, progress


def test_probe_sample(sample_video):
    info = probe(sample_video)
    assert (info.width, info.height) == (320, 240)
    assert info.fps == pytest.approx(10)
    assert info.duration == pytest.approx(2, abs=0.1)
    assert info.has_audio


def test_probe_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"pas une video")
    with pytest.raises(VideoError):
        probe(bad)


def test_error_messages_are_french_only_and_details_are_logged(tmp_path, caplog):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"pas une video")
    with caplog.at_level("WARNING", logger="jideo.video"), pytest.raises(VideoError) as exc:
        probe(bad)
    assert "/" not in str(exc.value)
    assert "Invalid" not in str(exc.value)
    assert any("Invalid" in r.getMessage() for r in caplog.records)


def test_extract_frame_and_thumbnail(sample_video, tmp_path):
    assert extract_frame(sample_video, 1.0).shape == (240, 320, 3)
    thumb = tmp_path / "t.jpg"
    make_thumbnail(sample_video, thumb)
    assert thumb.stat().st_size > 0


@pytest.mark.parametrize(
    ("size", "downscale", "expected"),
    [
        ((1920, 1080), True, (1280, 720)),
        ((1080, 1920), True, (720, 1280)),
        ((1280, 720), True, (1280, 720)),
        ((1920, 1080), False, (1920, 1080)),
        ((641, 481), False, (640, 480)),
    ],
)
def test_output_size(size, downscale, expected):
    assert output_size(*size, downscale) == expected


def test_process_keeps_fps_audio_and_notice(sample_video, tmp_path):
    dst = tmp_path / "out.mp4"
    stats, progress = run(sample_video, dst, tmp_path)
    info = probe(dst)
    assert info.fps == pytest.approx(10)
    assert info.duration == pytest.approx(2, abs=0.2)
    assert info.has_audio
    assert ffprobe_format(dst)["tags"]["comment"] == AI_NOTICE
    assert stats.frames_total == pytest.approx(20, abs=1)
    assert stats.frames_with_face == stats.frames_total
    assert progress[-1][0] == progress[-1][1] == stats.frames_total


def test_trim_processes_only_the_segment(sample_video, tmp_path):
    dst = tmp_path / "out.mp4"
    stats, _ = run(sample_video, dst, tmp_path, start=0.5, end=1.5)
    assert probe(dst).duration == pytest.approx(1, abs=0.2)
    assert stats.frames_total == pytest.approx(10, abs=1)


def test_frame_fn_output_is_encoded(sample_video, tmp_path):
    dst = tmp_path / "out.mp4"
    stats, _ = run(sample_video, dst, tmp_path, frame_fn=lambda f: (np.zeros_like(f), False))
    assert stats.frames_with_face == 0
    assert extract_frame(dst, 1.0).mean() < 5


def test_cancel_stops_and_leaves_no_output(sample_video, tmp_path):
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 5

    dst = tmp_path / "out.mp4"
    with pytest.raises(Cancelled):
        run(sample_video, dst, tmp_path, should_cancel=should_cancel)
    assert not dst.exists()


def test_empty_segment_is_rejected(sample_video, tmp_path):
    with pytest.raises(VideoError):
        run(sample_video, tmp_path / "out.mp4", tmp_path, start=1.5, end=1.0)


def test_silent_video(make_video, tmp_path):
    src = make_video(
        "silent.mp4", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    )
    dst = tmp_path / "out.mp4"
    run(src, dst, tmp_path)
    assert not probe(dst).has_audio


@pytest.mark.parametrize(("name", "extra"), [("full.mkv", []), ("full.mp4", ["-movflags", "+faststart"])])
def test_truncated_source_is_an_error(make_video, tmp_path, caplog, name, extra):
    # Le conteneur annonce 2 s (index/durée en tête de fichier) mais la moitié des octets manque.
    full = make_video(
        name, "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", *extra,
    )
    data = full.read_bytes()
    cut = tmp_path / ("cut" + full.suffix)
    cut.write_bytes(data[: len(data) // 2])
    assert probe(cut).duration == pytest.approx(2, abs=0.1)
    dst = tmp_path / "out.mp4"
    with caplog.at_level("WARNING", logger="jideo.video"), pytest.raises(VideoError, match="jusqu'au bout"):
        run(cut, dst, tmp_path)
    assert not dst.exists()
    assert any(r.name == "jideo.video" for r in caplog.records)


def test_audio_not_copyable_to_mp4_is_reencoded_to_aac(make_video, tmp_path):
    src = make_video(
        "mulaw.mkv", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_mulaw", "-shortest",
    )
    dst = tmp_path / "out.mp4"
    run(src, dst, tmp_path)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
         "-of", "csv=p=0", str(dst)],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "aac"


# --- Review Focus -----------------------------------------------------------

def test_rotated_video_is_handled_upright(make_video, tmp_path):
    src = make_video(
        "rotated.mp4", "-display_rotation:v:0", "90", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    )
    info = probe(src)
    assert (info.width, info.height) == (240, 320)
    assert extract_frame(src, 0.5).shape == (320, 240, 3)
    dst = tmp_path / "out.mp4"
    run(src, dst, tmp_path)
    assert (probe(dst).width, probe(dst).height) == (240, 320)


def test_webm_with_opus_keeps_audio(make_video, tmp_path):
    src = make_video(
        "clip.webm", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1",
        "-c:v", "libvpx", "-c:a", "libopus", "-shortest",
    )
    dst = tmp_path / "out.mp4"
    run(src, dst, tmp_path)
    assert probe(dst).has_audio


def test_odd_dimensions_are_made_even(make_video, tmp_path):
    src = make_video(
        "odd.mp4", "-f", "lavfi", "-i", "testsrc=size=321x241:rate=10", "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv444p",
    )
    dst = tmp_path / "out.mp4"
    run(src, dst, tmp_path)
    assert (probe(dst).width, probe(dst).height) == (320, 240)
