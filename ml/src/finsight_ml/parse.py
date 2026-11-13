"""Parse bank SMS text into a structured transaction. Regex-per-template first;
if nothing matches, callers may opt into an LLM JSON-schema extraction fallback
(stubbed — real LLM wiring lands in Phase 5, this just reserves the hook so the
rest of the pipeline can already branch on "needs fallback").
"""

import re
from dataclasses import dataclass
from datetime import datetime

DEBIT_VERB = r"(?:debited|sent|paid|dr\b)"
CREDIT_VERB = r"(?:credited|received|cr\b)"

_DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")


@dataclass
class ParsedTxn:
    amount_paise: int
    direction: str  # "DR" or "CR"
    vpa: str | None
    ref: str | None
    bank_label: str | None
    ts: datetime | None
    balance_paise: int | None
    raw_text: str


class LLMFallbackNotImplemented(Exception):
    """Raised when a message needs the (Phase 5) LLM extraction fallback."""


def _parse_amount(raw: str) -> int:
    return round(float(raw.replace(",", "")) * 100)


def _parse_datetime(date_str: str, time_str: str | None) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            date_part = datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if not time_str:
            return date_part
        for tfmt in ("%H:%M:%S", "%H:%M"):
            try:
                time_part = datetime.strptime(time_str, tfmt)
            except ValueError:
                continue
            return date_part.replace(
                hour=time_part.hour, minute=time_part.minute, second=time_part.second
            )
        return date_part
    return None


def _direction(text: str) -> str | None:
    if re.search(DEBIT_VERB, text, re.IGNORECASE):
        return "DR"
    if re.search(CREDIT_VERB, text, re.IGNORECASE):
        return "CR"
    return None


_CUR = r"(?:Rs\.?|INR|₹)"

_TEMPLATES = [
    # Kaveri National Bank (KNB)
    re.compile(
        _CUR
        + r"\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)\s+(?:debited|credited)\s+(?:from|to)\s+a/c\s*XX\d{2,6}\s+on\s+"
        r"(?P<date>\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+(?:to|from)\s+VPA\s+"
        r"(?P<vpa>\S+?)\.?\s*Ref\s*No\.?\s*(?P<ref>\w+)\.?"
        r"(?:\s*Avl\s*Bal\s*" + _CUR + r"\s*(?P<balance>[\d,]+(?:\.\d{1,2})?))?",
        re.IGNORECASE,
    ),
    # Trident Co-operative Bank (TCB)
    re.compile(
        r"(?:TCB).*?(?:sent|received)\s+"
        + _CUR
        + r"\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)\s+(?:to|from)\s+(?P<vpa>\S+)\s+on\s+"
        r"(?P<date>\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})\s+at\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+via\s+UPI\.?\s*"
        r"Txn\s*Ref\s*(?P<ref>\w+)\.?"
        + r"(?:\s*Bal:?\s*"
        + _CUR
        + r"\s*(?P<balance>[\d,]+(?:\.\d{1,2})?))?",
        re.IGNORECASE,
    ),
    # Sundial Bank (SDB)
    re.compile(
        r"SDB:?\s*"
        + _CUR
        + r"\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)\s+(?:paid\s+to|received\s+from)\s+(?P<vpa>\S+)\s+UPI\s*Ref\s*"
        r"(?P<ref>\w+)\s+on\s+(?P<date>\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\.?"
        + r"(?:\s*Available\s*balance\s*"
        + _CUR
        + r"\s*(?P<balance>[\d,]+(?:\.\d{1,2})?))?",
        re.IGNORECASE,
    ),
    # Meridian Grameen Bank (MGB)
    re.compile(
        r"MGB-UPI:?\s*"
        + _CUR
        + r"\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)\s+(?:debited\s+frm|credited\s+to)\s+a/c\s*\d{2,6}\s+"
        r"(?:to|from)\s+(?P<vpa>\S+)\s+on\s+(?P<date>\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}),\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*"
        r"hrs\.?\s*RRN\s*(?P<ref>\w+)\.?"
        + r"(?:\s*Bal\s*"
        + _CUR
        + r"\s*(?P<balance>[\d,]+(?:\.\d{1,2})?))?",
        re.IGNORECASE,
    ),
    # Parvat Bank (PVB)
    re.compile(
        r"PVB:?\s*"
        + _CUR
        + r"\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)\s*(?P<verb>dr|cr)\s+for\s+UPI/(?P<ref>\w+)/(?P<vpa>\S+?)\s+on\s+"
        r"(?P<date>\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})\.?\s*(?:Bal\s*"
        + _CUR
        + r"\s*(?P<balance>[\d,]+(?:\.\d{1,2})?))?",
        re.IGNORECASE,
    ),
]

_BANK_LABELS = ["KNB", "TCB", "SDB", "MGB", "PVB"]


def _extract_amount(match: re.Match[str], group: str = "amount") -> int | None:
    try:
        raw = match.group(group)
    except IndexError:
        return None
    return _parse_amount(raw) if raw else None


def parse_sms(text: str, use_llm_fallback: bool = False) -> ParsedTxn | None:
    """Parse a single bank SMS. Returns None (not an exception) when no
    template matches, so callers can cheaply count parse failures."""
    normalized = " ".join(text.split())

    for i, pattern in enumerate(_TEMPLATES):
        m = pattern.search(normalized)
        if not m:
            continue
        groups = m.groupdict()
        amount = _extract_amount(m)
        if amount is None:
            continue

        direction = _direction(groups.get("verb") or normalized)
        if direction is None:
            continue

        ts = _parse_datetime(groups.get("date", ""), groups.get("time"))
        balance_raw = groups.get("balance")
        balance_paise = _parse_amount(balance_raw) if balance_raw else None

        return ParsedTxn(
            amount_paise=amount,
            direction=direction,
            vpa=groups.get("vpa"),
            ref=groups.get("ref"),
            bank_label=_BANK_LABELS[i],
            ts=ts,
            balance_paise=balance_paise,
            raw_text=text,
        )

    if use_llm_fallback:
        raise LLMFallbackNotImplemented(
            "LLM JSON-schema extraction fallback is not wired up until Phase 5"
        )
    return None
