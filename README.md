# Invoice Extraction Pipeline

Reads a vendor invoice (PDF, JPG or PNG) and returns validated, structured JSON.
Non-invoices are detected, and bad input or API failures are reported without crashing a batch.

## How it works

1. **Extract.** The file is sent straight to Gemini (`gemini-3.1-flash-lite` by default) as a vision input,
   with a system prompt that holds the labelling rules and the JSON schema. Vision input handles clean PDFs,
   scans and phone photos in one step, with no separate OCR stage to maintain.
2. **Validate.** The reply must parse as JSON and match the Pydantic schema (`src/schema.py`).
   For invoices, `src/validate.py` also checks that required fields are present and that
   line items + tax = total within a tolerance of 0.5.
3. **Retry or flag.** If a check fails, the model is called once more with the problems listed.
   If it still fails, the output is returned with `status: needs_review`. Bad data is never passed on silently.

### Bad-input handling

- **Non-invoices:** `is_invoice: false` and every other field `null`.
- **Corrupt, empty, oversized or unsupported files:** rejected before any API call, with a clear message.
- **API failures:** 429, 5xx and timeouts are retried with backoff. Billing, key or model-name errors (4xx) stop at once.
  One failing document never stops a batch. It is recorded as `status: error`.

## Setup (from a fresh clone)

~~~bat
git clone https://github.com/aryanchouhan22/invoice-extraction-pipeline.git
cd invoice-extraction-pipeline
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
~~~

macOS or Linux: `source .venv/bin/activate` and `cp .env.example .env`.

Open `.env` and set `GEMINI_API_KEY` (a free key from https://aistudio.google.com).
Never commit `.env`.

The sample documents are confidential and are not in this repo. Put the sample pack in `data/`
so that these paths exist: `data/labelled/L01.pdf`, `data/labelled/L01.json`, `data/unlabelled/U01.pdf`, and so on.

## Run

One document (the JSON goes to stdout, status lines go to stderr):

~~~bat
python extract.py data\labelled\L01.pdf > out.json
~~~

A folder, writing `outputs/<name>.json` plus `outputs/meta/<name>.json` (status, tokens, cost, problems):

~~~bat
python extract.py data\unlabelled --out outputs --skip-existing
~~~

Evaluate on the 10 labelled documents (one command, prints the results table):

~~~bat
python eval.py
~~~

Re-score the saved outputs without calling the API: `python eval.py --cached`.
Re-run only documents that errored: `python eval.py --retry-errors`.

## Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `GEMINI_API_KEY` | Your API key |
| `MODEL_NAME` | Model to use |
| `PRICE_INPUT_PER_M`, `PRICE_OUTPUT_PER_M` | USD per 1M tokens, used for the notional cost figure |
| `REQUEST_DELAY_S` | Pause between documents in a batch (free-tier rate limits) |

## Layout

~~~
extract.py        CLI extractor
eval.py           eval harness
src/schema.py     Pydantic schema
src/validate.py   parsing and business-rule checks
src/prompts.py    system and retry prompts
src/llm.py        Gemini call with retry and backoff
src/pipeline.py   file checks, retry loop, result files
outputs/          JSON for all 20 documents, outputs/meta/ for run details
REPORT.md         approach, accuracy, failure analysis, cost
~~~