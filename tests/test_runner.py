from __future__ import annotations

import sys
from pathlib import Path

import pytest

from local_n8n.core.runner import run_streaming


def test_run_streaming_streams_combined_output_to_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run_streaming(
        [
            sys.executable,
            "-c",
            "import sys; print('stdout line'); print('stderr line', file=sys.stderr)",
        ],
        cwd=tmp_path,
    )

    captured = capsys.readouterr()

    assert result.returncode == 0
    assert result.stdout == ""
    assert "stdout line" in result.stderr
    assert "stderr line" in result.stderr
    assert "stdout line" in captured.err
    assert "stderr line" in captured.err
