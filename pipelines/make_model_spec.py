"""Emit an Azure ML model specification with the gate metrics as tags.

Shell quoting of a dozen float tags through ``az ml model update --set`` is
fragile, so the workflow generates a spec file instead:

    python pipelines/make_model_spec.py \
        --name drg-champion --path ./job-output/artifacts/models \
        --tags model_tags.json --out model-spec.yml

    az ml model create -f model-spec.yml
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

SCHEMA = "https://azuremlschemas.azureedge.net/latest/model.schema.json"


def build_spec(name: str, path: str, tags: dict[str, str], description: str | None = None) -> dict:
    return {
        "$schema": SCHEMA,
        "name": name,
        "path": path,
        "type": "custom_model",
        "description": description
        or "DRG champion forecaster: half-hourly neighbourhood demand with statistical stress alerting.",
        # Azure ML tag values must be strings and are length-limited
        "tags": {str(k): str(v)[:250] for k, v in tags.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an Azure ML model spec")
    parser.add_argument("--name", required=True)
    parser.add_argument("--path", required=True, help="Folder containing the model artifact")
    parser.add_argument("--tags", default=None, help="JSON file of tags (from promote_model.py)")
    parser.add_argument("--description", default=None)
    parser.add_argument("--out", default="model-spec.yml")
    args = parser.parse_args()

    tags = json.loads(Path(args.tags).read_text(encoding="utf-8")) if args.tags else {}
    spec = build_spec(args.name, args.path, tags, args.description)

    Path(args.out).write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    print(f"wrote {args.out} with {len(spec['tags'])} tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
