"""CLI / demo smoke tests."""

from __future__ import annotations

from pathlib import Path

from flashframe.cli import main


def test_demo_cli(tmp_path: Path):
    outdir = tmp_path / "evidence"
    rc = main(["demo", "--outdir", str(outdir), "--size", "8", "--frame-ms", "20"])
    assert rc == 0
    assert (outdir / "demo_rebuilt.png").exists()
    assert (outdir / "transmit_timeline.json").exists()
    assert (outdir / "signal.csv").exists()
    assert (outdir / "roundtrip.json").exists()
