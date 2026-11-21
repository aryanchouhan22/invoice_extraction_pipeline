import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator


class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    amount: float


class Invoice(BaseModel):
    is_invoice: bool
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # YYYY-MM-DD
    currency: Optional[str] = None      # ISO 4217
    line_items: Optional[List[LineItem]] = None
    tax_total: Optional[float] = None
    total: Optional[float] = None

    @field_validator("invoice_date")
    @classmethod
    def _check_date(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"invoice_date must be YYYY-MM-DD, got {v!r}")
        return v

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", v):
            raise ValueError(f"currency must be a 3-letter ISO code, got {v!r}")
        return v

    @model_validator(mode="after")
    def _non_invoice_is_all_null(self):
        if not self.is_invoice:
            self.vendor = None
            self.invoice_number = None
            self.invoice_date = None
            self.currency = None
            self.line_items = None
            self.tax_total = None
            self.total = None
        return self