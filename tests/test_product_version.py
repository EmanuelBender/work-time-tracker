import json
import re
from pathlib import Path

from worktime import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_product_version_has_one_source_of_truth():
    version = (ROOT / "worktime" / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "manu-control.json").read_text(encoding="utf-8"))

    assert re.fullmatch(r"(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*)){2}(?:-[0-9A-Za-z.-]+)?", version)
    assert __version__ == version
    assert manifest["versionFile"] == "worktime/VERSION"
    assert "version" not in manifest
