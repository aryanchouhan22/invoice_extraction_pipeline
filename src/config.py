import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("MODEL_NAME", "gemini-3.1-flash-lite")
PRICE_IN = float(os.getenv("PRICE_INPUT_PER_M", "0.25"))    # USD per 1M input tokens
PRICE_OUT = float(os.getenv("PRICE_OUTPUT_PER_M", "1.50"))  # USD per 1M output tokens
REQUEST_DELAY_S = float(os.getenv("REQUEST_DELAY_S", "6"))  # pause between documents (free-tier rate limit)

TIMEOUT_S = 90
MAX_API_RETRIES = 4          # retries for 429 / 5xx / timeouts
MAX_EXTRACT_ATTEMPTS = 2     # 1 normal try + 1 retry when validation fails
MAX_FILE_MB = 15
TOTAL_TOLERANCE = 0.5        # line items + tax vs total: allows round-off to the nearest whole unit