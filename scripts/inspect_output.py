from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect book ingestion output artifacts")
    parser.add_argument("--output", required=True, help="Output directory path")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    output_dir = Path(args.output)
    manifest_path = output_dir / "book.manifest.json"
    summary_path = output_dir / "book.summary.json"

    if not output_dir.exists():
        print(f"[error] output directory does not exist: {output_dir}", file=sys.stderr)
        raise SystemExit(1)

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print("[inspect] manifest page order:")
        for page in manifest.get("pages", []):
            print(f"  {int(page['page_number']):04d} -> {page['source_file']}")
    else:
        print("[warn] manifest missing", file=sys.stderr)

    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print("[inspect] summary json:")
        print(json.dumps(summary, indent=2))
    else:
        print("[warn] summary missing", file=sys.stderr)

    print("[inspect] output files:")
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        print(f"  {path.relative_to(output_dir)}")


if __name__ == "__main__":
    main()
