# Report

## Approach

- **Model:** `gemini-3.1-flash-lite` (Google Gemini API, free tier). I chose a small, cheap vision model because
  the task is structured reading and not hard reasoning.
- **Input:** the file is sent directly to the model as a vision input (PDF or image). There is no separate OCR step,
  so clean PDFs, scans and phone photos go through one path.
- **Prompt:** one system prompt that holds the labelling conventions from the sample pack (seller as vendor, issue date
  and not due date, discounts as negative rows, tax_total as the sum of all tax lines, 0 when no tax is shown), an
  instruction to copy numbers as printed, and the JSON Schema. The reply is requested as JSON.
- **Validation:** the reply must parse and match the Pydantic schema (ISO date, 3-letter currency, non-invoice means all
  other fields null). For invoices, required fields must be present and line items + tax must equal the total within 0.5.
- **On failure:** one retry with the failed checks added to the prompt. If it still fails, the output is returned with
  `status: needs_review`. Nothing is passed on silently.
- **Overfitting:** the prompt was written once from the sample pack README and was **not tuned against the labelled
  documents**. I did not change it after seeing results.

### What did not work

- My first retry code caught timeouts only from the `httpx` package. The Google SDK in my environment uses a renamed
  copy of it, so a read timeout on a labelled document escaped the retry logic and crashed the whole eval run.
  I now match network errors by class name and catch any error per document, so one bad document cannot stop a batch.
- Setup also failed in ways unrelated to extraction: a 403 (free tier not available for the first key's project) and a
  404 (`gemini-2.5-flash` no longer available to new users). I switched to a new key and to `gemini-3.1-flash-lite`.

## Matching rules (eval)

| Field | Rule |
|---|---|
| is_invoice | exact boolean |
| vendor | lowercase, strip punctuation and legal suffixes (Ltd, Pvt, Inc, GmbH...), then exact. "Acme Pvt Ltd" = "Acme" |
| invoice_number | ignore spaces, `#` and case; otherwise exact |
| invoice_date | exact `YYYY-MM-DD` |
| currency | exact, case-insensitive |
| tax_total, total | equal within 0.01, so `1,200.00` = `1200` |
| line_items | same row count; rows compared in printed order; each row needs the same amount and quantity (within 0.01) and a description with at least 80% text similarity |
| null fields | null matches only null (non-invoices must be all null) |

The 80% description similarity and the 0.01 tolerance are lenient choices. A row-level score is also reported.

## Accuracy (10 labelled documents)

First run: 8 of 10 documents were processed. L07 and L09 failed with `503 UNAVAILABLE` ("high demand") from the API on
all 5 tries, so they got no output and counted as wrong (80% on every field). I then re-ran only the errored documents
with the same code and prompt (`python eval.py --retry-errors`), and they succeeded.

| Field | Correct | Accuracy |
|---|---|---|
| is_invoice | 10/10 | 100% |
| vendor | 10/10 | 100% |
| invoice_number | 10/10 | 100% |
| invoice_date | 10/10 | 100% |
| currency | 10/10 | 100% |
| line_items | 10/10 | 100% (66/66 rows) |
| tax_total | 10/10 | 100% |
| total | 10/10 | 100% |

Caveats: 10 documents is a small sample. 100% here does not mean the extractor is perfect on harder scans, other
layouts or other languages. I have no evidence on how it behaves outside this set.

## Failure analysis

I found **no extraction errors** on the labelled set. The real failures were:

| Cause | Examples | Handling |
|---|---|---|
| Provider overload (503) | L07, L09 on the first run | retries with backoff, then `status: error`; re-run of failed documents only |
| Unhandled timeout class | crash of the eval run | fixed by matching error class names and catching errors per document |
| Account and setup | 403 free tier unavailable, 404 retired model | new key, new model |

For the 10 unlabelled documents I have no ground truth, so I spot-checked. Day/month ambiguity was the main risk:
U09 prints `07/02/2026` with due date `21/02/2026`, which proves day-first, and the output is `2026-02-07`, correct.
U03 (`Nov 03, 2026`) and U04 (`2026-07-01`) were also correct.
TODO: say what you found when comparing U02 (scan) with its output, and confirm U06 and U10 are non-invoices.

**Review flag:** all 20 documents were `ok`, so the flag never fired on real data, and I cannot show whether flagged
documents hold the errors. I only tested the check on a made-up invoice with a wrong total, which it caught:
`line items (100.0) + tax (18.0) = 118.0 but total is 999.0`. The totals check does not catch wrong dates, vendors or
invoice numbers, so `ok` is not a guarantee.

**Bad inputs tested:** corrupt PDF, empty file and `.txt` file are rejected before any API call with a clear message;
an invalid API key gives a clean `error` with no retry loop. Non-invoices return `is_invoice: false` with all other
fields null.

**What I would fix first:**
1. Reliability: longer backoff and a fallback model for 503s, since this caused every real failure.
2. A larger and harder labelled set (more scans and photos), since the current set cannot show weaknesses.
3. A cross-check of the invoice date against the due date to catch day/month swaps.

## Cost per document

- **Method:** token counts come from the API's `usage_metadata` (prompt tokens as input; response plus thinking tokens as
  output), summed per document across all attempts, priced at list price: $0.25 per 1M input and $1.50 per 1M output
  tokens (from Google's pricing page; verify). The free tier bills $0, so these figures are notional.
- **Result over all 20 documents:** 28,116 tokens in and 5,972 out, an average of 1,406 in and 299 out per document,
  about $0.0160 in total and **about $0.0008 per document**.
- Not included: development runs and the two 503 attempts, which returned no usage data.