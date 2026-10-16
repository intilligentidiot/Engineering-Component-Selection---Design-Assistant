"""
Unit conversions used on screen (static/js/units.js). The calculations never use
these — they only convert values for display and input — but a wrong factor
would show wrong numbers, so every factor is checked against known values.
Runs with Node.js when it is installed; skipped otherwise.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_unit_conversion_factors():
    out = subprocess.run(["node", str(ROOT / "tests/js/units_check.js"), str(ROOT / "static/js/units.js")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "ALL OK" in out.stdout, out.stdout
