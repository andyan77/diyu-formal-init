from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.gateway.api.app import create_app

_CONTRACT = Path(__file__).resolve().parents[3] / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = (
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if args.check:
        if not _CONTRACT.exists() or _CONTRACT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("openapi.json is out of date; run make openapi")
        return
    _CONTRACT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
