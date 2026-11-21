import argparse
import json
import sys
import time
from pathlib import Path

from src import config
from src.pipeline import SUPPORTED, extract_document, save_result


def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED)
        else:
            files.append(p)
    return files


def main():
    ap = argparse.ArgumentParser(description="Extract invoice JSON from PDFs or images.")
    ap.add_argument("paths", nargs="+", help="files and/or folders")
    ap.add_argument("--out", help="write JSON files to this folder (needed for more than one file)")
    ap.add_argument("--skip-existing", action="store_true", help="skip documents that already have an output")
    args = ap.parse_args()

    files = collect(args.paths)
    if not files:
        sys.exit("no documents found")
    if len(files) > 1 and not args.out:
        sys.exit("more than one document: pass --out outputs")

    failures = 0
    for i, f in enumerate(files):
        if args.out and args.skip_existing and (Path(args.out) / "meta" / f"{f.stem}.json").exists():
            print(f"[skip] {f.name}", file=sys.stderr)
            continue

        inv, meta = extract_document(f)
        print(
            f"[{meta['status']}] {f.name}  attempts={meta['attempts']}  "
            f"tokens={meta['tokens_in']}/{meta['tokens_out']}  notional_cost=${meta['cost_usd']:.5f}",
            file=sys.stderr,
        )
        for p in meta["problems"]:
            print(f"    - {p}", file=sys.stderr)
        if meta["error"]:
            print(f"    ! {meta['error']}", file=sys.stderr)
        if meta["status"] != "ok":
            failures += 1

        if args.out:
            save_result(f.stem, inv, meta, args.out)
        elif inv is not None:
            print(json.dumps(inv.model_dump(mode="json"), indent=2))

        if args.out and i < len(files) - 1:
            time.sleep(config.REQUEST_DELAY_S)

    sys.exit(1 if failures and not args.out and len(files) == 1 else 0)


if __name__ == "__main__":
    main()