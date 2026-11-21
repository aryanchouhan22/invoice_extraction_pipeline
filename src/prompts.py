import json

from .schema import Invoice

_SCHEMA = json.dumps(Invoice.model_json_schema())

SYSTEM_PROMPT = f"""You extract structured data from business documents: clean PDFs, scans and phone photos.
Return ONLY one JSON object. No prose, no markdown.

Rules, follow them exactly:
- is_invoice: true only if the document is an invoice. Anything else (bank statement, purchase order, letter, etc.)
  is not an invoice: set is_invoice to false and every other field to null.
- vendor: the seller who issued the invoice, as printed at the top. Not the customer or bill-to party.
- invoice_number: as printed, as a string.
- invoice_date: the date the invoice was issued, as YYYY-MM-DD. Not the due date, order date or PO date.
  Decide day-first or month-first from the document's context (other dates, locale, currency).
- currency: ISO 4217 code such as INR, USD, EUR, GBP. Infer it from symbols and context.
- line_items: one object per row of the item table, in the printed order.
  description as printed. quantity as printed, or null if the row has no quantity.
  amount is the row total BEFORE tax.
  Charges (shipping, fees) shown as rows are line items too. A discount row is a negative amount.
- tax_total: the sum of ALL tax lines (GST, CGST+SGST, VAT, etc.). Use 0 if tax is zero or not shown.
- total: the final amount payable, including tax.
- Numbers are plain JSON numbers: no thousands separators, no currency symbols.
- Never invent values. If something is not printed and cannot be derived from the rules above, use null.
- Copy numbers exactly as printed. Do not adjust them so that the totals add up.

The JSON must match this JSON Schema:
{_SCHEMA}
"""


def user_prompt(previous_problems=None) -> str:
    if not previous_problems:
        return "Extract the data from the attached document."
    issues = "\n".join(f"- {p}" for p in previous_problems)
    return (
        "Extract the data from the attached document.\n"
        "Your previous answer failed these checks:\n"
        f"{issues}\n"
        "Re-read the document carefully and return corrected JSON. "
        "If the document itself is inconsistent, return exactly what is printed."
    )