"""Regenerate openapi.yaml from the app: python tools/dump_openapi.py"""
import os
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fixit.api.app import create_app  # noqa: E402


def spec() -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        return create_app(os.path.join(d, "x.db")).openapi()


if __name__ == "__main__":
    Path(__file__).resolve().parents[1].joinpath("openapi.yaml").write_text(yaml.safe_dump(spec(), sort_keys=True), encoding="utf-8")
