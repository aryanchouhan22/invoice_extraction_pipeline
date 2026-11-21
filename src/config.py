import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("MODEL_NAME", "gemini-2.5-flash")
PRICE_IN = float(os.getenv("PRICE_INPUT_PER_M", "0.30"))
PRICE_OUT = float(os.getenv("PRICE_OUTPUT_PER_M", "2.50"))
REQUEST_DELAY_S = float(os.getenv("REQUEST_DELAY_S", "6"))  # stay under free-tier RPM

TIMEOUT_S = 90
MAX_API_RETRIES = 4         # for 429 / 5xx / timeouts
MAX_EXTRACT_ATTEMPTS = 2    # 1 normal try + 1 retry when validation fails
MAX_FILE_MB = 15