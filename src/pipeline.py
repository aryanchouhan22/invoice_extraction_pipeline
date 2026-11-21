import json
from pathlib import Path

from . import config, llm, prompts, validate

MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
SUPPORTED = set(MIME)


class InputError(Exception):
    pass


def load_file(path):
    p = Path(path)
    if not p.is_file():
        raise InputError("file not found")
    mime = MIME.get(p.suffix.lower())
    if mime is None:
        raise InputError(f"unsupported file type {p.suffix!r}")
    data = p.read_bytes()
    if not data:
        raise InputError("file is empty")
    if len(data) > config.MAX_FILE_MB * 1024 * 1024:
        raise InputError(f"file larger than {config.MAX_FILE_MB} MB")
    if mime == "application/pdf" and not data.lstrip().startswith(b"%PDF"):
        raise InputError("corrupt PDF (missing %PDF header)")
    if mime == "image/jpeg" and data[:2] != b"\xff\xd8":
        raise InputError("corrupt JPEG (bad header)")
    if mime == "image/png" and data[:8] != b"\x89PNG\r\n\x1a\n":
        raise InputError("corrupt PNG (bad header)")
    return data, mime


def cost_usd(tokens_in, tokens_out):
    return tokens_in / 1e6 * config.PRICE_IN + tokens_out / 1e6 * config.PRICE_OUT


def extract_document(path):
    """Returns (Invoice or None, meta dict). Never raises for a bad document or API failure."""
    meta = {
        "file": Path(path).name,
        "status": "error",          # ok | needs_review | error
        "needs_review": True,
        "attempts": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "problems": [],
        "error": None,
        "model": config.MODEL,
    }

    try:
        data, mime = load_file(path)
    except InputError as e:
        meta["error"] = f"bad input: {e}"
        return None, meta

    best = None
    previous_problems = None
    for attempt in range(1, config.MAX_EXTRACT_ATTEMPTS + 1):
        meta["attempts"] = attempt
        try:
            text, tin, tout = llm.generate(data, mime, prompts.user_prompt(previous_problems))
        except Exception as e:
            meta["error"] = str(e)
            break
        meta["tokens_in"] += tin
        meta["tokens_out"] += tout

        inv, problems = validate.parse_and_validate(text)
        if inv is not None:
            best = inv
        meta["problems"] = problems
        if not problems:
            meta["status"] = "ok"
            meta["needs_review"] = False
            break
        previous_problems = problems

    if meta["status"] != "ok" and best is not None:
        meta["status"] = "needs_review"   # we return the data, clearly flagged, never silently
    meta["cost_usd"] = round(cost_usd(meta["tokens_in"], meta["tokens_out"]), 6)
    return best, meta


def save_result(stem, invoice, meta, out_dir):
    out = Path(out_dir)
    (out / "meta").mkdir(parents=True, exist_ok=True)
    inv_path = out / f"{stem}.json"
    if invoice is not None:
        inv_path.write_text(
            json.dumps(invoice.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        inv_path.unlink(missing_ok=True)  # no stale output from an earlier run
    (out / "meta" / f"{stem}.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )