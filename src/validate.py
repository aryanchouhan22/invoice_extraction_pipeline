import json

from pydantic import ValidationError

from . import config
from .schema import Invoice


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def check_rules(inv: Invoice) -> list:
    """Business-rule checks on a schema-valid invoice. Returns a list of problems."""
    problems = []
    if not inv.is_invoice:
        return problems

    for name in ("vendor", "invoice_number", "invoice_date", "currency", "total"):
        if getattr(inv, name) is None:
            problems.append(f"{name} is null for an invoice")
    if inv.tax_total is None:
        problems.append("tax_total is null (it should be 0 when the document shows no tax)")
    if not inv.line_items:
        problems.append("line_items is missing or empty for an invoice")

    if inv.total is not None and inv.line_items:
        items = round(sum(li.amount for li in inv.line_items), 2)
        tax = inv.tax_total or 0.0
        diff = round(items + tax - inv.total, 2)
        if abs(diff) > config.TOTAL_TOLERANCE:
            problems.append(
                f"line items ({items}) + tax ({tax}) = {round(items + tax, 2)} "
                f"but total is {inv.total} (difference {diff})"
            )
    return problems


def parse_and_validate(raw_text: str):
    """Returns (Invoice or None, problems). None means the output could not be parsed at all."""
    try:
        data = json.loads(_strip_fences(raw_text))
    except json.JSONDecodeError as e:
        return None, [f"Output is not valid JSON: {e}"]
    try:
        inv = Invoice.model_validate(data)
    except ValidationError as e:
        msgs = [f"schema error at {'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        return None, msgs
    return inv, check_rules(inv)