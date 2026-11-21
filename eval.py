import argparse
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

from src import config
from src.pipeline import SUPPORTED, cost_usd, extract_document, save_result

LABELLED = Path("data/labelled")
OUT = Path("outputs")
FIELDS = ["is_invoice", "vendor", "invoice_number", "invoice_date",
          "currency", "line_items", "tax_total", "total"]
SHORT = {"is_invoice": "inv?", "vendor": "vendor", "invoice_number": "number",
         "invoice_date": "date", "currency": "curr", "line_items": "items",
         "tax_total": "tax", "total": "total"}

LEGAL_SUFFIXES = {"ltd", "limited", "pvt", "private", "inc", "incorporated", "llc", "llp",
                  "co", "corp", "corporation", "gmbh", "plc", "company", "pte", "sa"}


# ---------- matching rules (stated in the report) ----------
def norm_text(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s).lower()).split())


def norm_vendor(s):
    words = [w for w in norm_text(s).split() if w not in LEGAL_SUFFIXES]
    return " ".join(words)


def norm_number(s):
    return re.sub(r"[\s#]+", "", str(s)).upper()


def num_close(a, b, tol=0.01):
    return abs(float(a) - float(b)) <= tol


def item_match(p, g):
    if not num_close(p["amount"], g["amount"]):
        return False
    pq, gq = p.get("quantity"), g.get("quantity")
    if (pq is None) != (gq is None):
        return False
    if pq is not None and not num_close(pq, gq):
        return False
    return SequenceMatcher(None, norm_text(p["description"]), norm_text(g["description"])).ratio() >= 0.8


def compare(field, pred, gold):
    """True if the predicted field matches the ground truth under our rules."""
    if gold is None or pred is None:
        return gold is None and pred is None
    if field == "is_invoice":
        return bool(pred) == bool(gold)
    if field == "vendor":
        return norm_vendor(pred) == norm_vendor(gold)
    if field == "invoice_number":
        return norm_number(pred) == norm_number(gold)
    if field == "invoice_date":
        return str(pred) == str(gold)
    if field == "currency":
        return str(pred).strip().upper() == str(gold).strip().upper()
    if field in ("tax_total", "total"):
        return num_close(pred, gold)
    if field == "line_items":
        return len(pred) == len(gold) and all(item_match(p, g) for p, g in zip(pred, gold))
    return pred == gold


def row_stats(pred, gold):
    """(matched rows, gold rows) for line items, paired by printed order."""
    if not gold:
        return 0, 0
    pred = pred or []
    return sum(item_match(p, g) for p, g in zip(pred, gold)), len(gold)


# ---------- running ----------
def find_documents():
    docs = []
    for gold_file in sorted(LABELLED.glob("*.json")):
        for ext in SUPPORTED:
            f = gold_file.with_suffix(ext)
            if f.exists():
                docs.append((gold_file.stem, f, gold_file))
                break
    return docs


def get_prediction(stem, path, cached):
    if cached:
        pj, mj = OUT / f"{stem}.json", OUT / "meta" / f"{stem}.json"
        pred = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else None
        meta = json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else {
            "status": "error", "needs_review": True, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0.0, "attempts": 0, "problems": [], "error": "no cached output"}
        return pred, meta
    inv, meta = extract_document(path)
    save_result(stem, inv, meta, OUT)
    return (inv.model_dump(mode="json") if inv else None), meta


def short(v, n=60):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 3] + "..."


def main():
    ap = argparse.ArgumentParser(description="Evaluate the extractor on the labelled documents.")
    ap.add_argument("--cached", action="store_true",
                    help="re-score outputs/ without calling the API")
    ap.add_argument("--retry-errors", action="store_true",
                    help="reuse saved outputs, but call the API again for documents that errored")
    args = ap.parse_args()

    docs = find_documents()
    if not docs:
        sys.exit(f"no labelled documents found in {LABELLED}")

    results = []
    for i, (stem, path, gold_file) in enumerate(docs):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))

        called_api = False
        if args.retry_errors:
            pred, meta = get_prediction(stem, path, True)
            if meta["status"] == "error":
                pred, meta = get_prediction(stem, path, False)
                called_api = True
        else:
            pred, meta = get_prediction(stem, path, args.cached)
            called_api = not args.cached
        # recompute cost with the current prices so every document uses the same ones
        meta["cost_usd"] = round(cost_usd(meta["tokens_in"], meta["tokens_out"]), 6)

        ok = {f: (pred is not None and compare(f, pred.get(f), gold.get(f))) for f in FIELDS}
        results.append({"doc": stem, "ok": ok, "pred": pred, "gold": gold, "meta": meta})
        print(f"  done {stem}: {meta['status']}  {meta.get('error') or ''}", file=sys.stderr)

        if called_api and i < len(docs) - 1:
            time.sleep(config.REQUEST_DELAY_S)

    # ---- per-document table ----
    cols = [SHORT[f] for f in FIELDS]
    header = f"{'doc':<6}" + "".join(f"{c:<8}" for c in cols) + f"{'status':<14}{'cost$':<9}"
    print(f"\nModel: {config.MODEL}   labelled documents: {len(results)}\n")
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r['doc']:<6}" + "".join(f"{('Y' if r['ok'][f] else 'N'):<8}" for f in FIELDS)
        row += f"{r['meta']['status']:<14}{r['meta']['cost_usd']:<9.5f}"
        print(row)

    # ---- per-field accuracy ----
    n = len(results)
    print("\nField-level accuracy")
    print("-" * 32)
    field_acc = {}
    for f in FIELDS:
        c = sum(r["ok"][f] for r in results)
        field_acc[f] = c / n
        print(f"{f:<16}{c:>2}/{n:<3}{100 * c / n:>6.1f}%")
    mr, tr = 0, 0
    for r in results:
        a, b = row_stats((r["pred"] or {}).get("line_items"), r["gold"].get("line_items"))
        mr += a
        tr += b
    if tr:
        print(f"{'line rows':<16}{mr:>2}/{tr:<3}{100 * mr / tr:>6.1f}%  (row-level, paired by order)")
    overall = sum(sum(r["ok"].values()) for r in results) / (n * len(FIELDS))
    print(f"{'all fields':<16}{'':<6}{100 * overall:>6.1f}%")

    # ---- errors ----
    print("\nMismatches")
    print("-" * 32)
    any_err = False
    for r in results:
        for f in FIELDS:
            if not r["ok"][f]:
                any_err = True
                p = None if r["pred"] is None else r["pred"].get(f)
                print(f"{r['doc']} {f}: predicted {short(p)} | expected {short(r['gold'].get(f))}")
        if r["meta"].get("error"):
            print(f"{r['doc']} ERROR: {r['meta']['error']}")
    if not any_err:
        print("none")

    # ---- review flag check (bonus) ----
    wrong = [r for r in results if not all(r["ok"].values())]
    flagged = [r for r in results if r["meta"]["status"] != "ok"]
    wrong_flagged = [r for r in wrong if r["meta"]["status"] != "ok"]
    print("\nReview-flag check")
    print("-" * 32)
    print(f"documents with at least one wrong field: {len(wrong)}/{n}")
    print(f"documents flagged needs_review or error: {len(flagged)}/{n}")
    print(f"wrong documents that were flagged:       {len(wrong_flagged)}/{len(wrong)}")
    print(f"flagged documents that were all correct: {len(flagged) - len(wrong_flagged)}/{len(flagged)}")

    # ---- cost ----
    tin = sum(r["meta"]["tokens_in"] for r in results)
    tout = sum(r["meta"]["tokens_out"] for r in results)
    cost = sum(r["meta"]["cost_usd"] for r in results)
    att = sum(r["meta"]["attempts"] for r in results)
    print("\nCost (notional, at list price; the free tier bills $0)")
    print("-" * 32)
    print(f"total tokens in/out: {tin}/{tout}   API calls: {att}")
    print(f"average per document: {tin / n:.0f} in, {tout / n:.0f} out, ${cost / n:.5f}")
    print(f"prices used: ${config.PRICE_IN}/1M in, ${config.PRICE_OUT}/1M out")

    OUT.mkdir(exist_ok=True)
    (OUT / "eval_results.json").write_text(json.dumps({
        "model": config.MODEL,
        "field_accuracy": field_acc,
        "overall": overall,
        "avg_tokens_in": tin / n, "avg_tokens_out": tout / n, "avg_cost_usd": cost / n,
        "documents": [{"doc": r["doc"], "ok": r["ok"], "status": r["meta"]["status"]} for r in results],
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()