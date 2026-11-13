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
    parse_method: str = "template"  # "template" | "generic"
    confidence: float = 1.0


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


# --------------------------------------------------------------------------
# Generic, template-free extractor — pulls each entity independently rather
# than matching one bank's whole message shape. Used when none of the 5
# known templates match. Lower confidence than a template hit (those are
# exact), scored by how many optional fields it could confirm.
# --------------------------------------------------------------------------

_REJECT_RE = re.compile(
    r"\bOTP\b|will be debited|is due\b|due on\b|\boffer\b|cashback\s+(?:up\s*to|upto)|"
    r"\breminder\b|auto-?pay|\bexpire\b|\brenew\b|selected for|click here|download our app|"
    r"withdrawn using your debit card",
    re.IGNORECASE,
)

_GENERIC_AMOUNT_RE = re.compile(
    r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE
)
_GENERIC_DEBIT_RE = re.compile(
    r"\b(?:debited|sent|paid|withdrawn|spent)\b", re.IGNORECASE
)
_GENERIC_CREDIT_RE = re.compile(
    r"\b(?:credited|received|deposited|refunded?)\b", re.IGNORECASE
)
_VPA_RE = re.compile(
    r"\b[\w.]+@[\w.\-]+\b"
)  # no hyphen in the local part — avoids swallowing a "UPI-" label prefix
_NAME_RE = re.compile(r"(?:\bto\b|\bfrom\b)\s+([A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)+)\b")
_REF_RE = re.compile(
    r"(?:Ref(?:\s*No)?|RRN|UPI\s*Ref|Txn\s*ID)\s*(?:is\s*)?[:\s]*([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_BALANCE_RE = re.compile(
    r"(?:Avl\.?\s*Bal(?:ance)?|Available\s*bal(?:ance)?|Bal(?:ance)?)[:\s]*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_GENERIC_DATE_RE = re.compile(
    r"(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\b)"
)
_GENERIC_TIME_RE = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*(am|pm|AM|PM)?")

_GENERIC_DATE_FORMATS = (*_DATE_FORMATS, "%d %b")


def _parse_generic_date(date_str: str) -> datetime | None:
    for fmt in _GENERIC_DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if fmt == "%d %b":
            dt = dt.replace(
                year=2026
            )  # no year in the message — this dataset is all 2026
        return dt
    return None


def _parse_generic_time(
    time_str: str, meridiem: str | None
) -> tuple[int, int, int] | None:
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            candidate = (
                f"{time_str} {meridiem}"
                if meridiem and "%p" in fmt and " " in fmt
                else (f"{time_str}{meridiem}" if meridiem and "%p" in fmt else time_str)
            )
            t = datetime.strptime(candidate, fmt)
            return t.hour, t.minute, t.second
        except ValueError:
            continue
    return None


def _parse_generic(text: str) -> ParsedTxn | None:
    if _REJECT_RE.search(text):
        return None

    amount_match = _GENERIC_AMOUNT_RE.search(text)
    if not amount_match:
        return None
    amount = _parse_amount(amount_match.group(1))

    direction = None
    if _GENERIC_DEBIT_RE.search(text):
        direction = "DR"
    elif _GENERIC_CREDIT_RE.search(text):
        direction = "CR"
    if direction is None:
        return None

    vpa_match = _VPA_RE.search(text)
    name_match = None if vpa_match else _NAME_RE.search(text)
    if vpa_match is None and name_match is None:
        return None
    counterparty = vpa_match.group(0) if vpa_match else name_match.group(1)

    confidence = 0.6

    date_match = _GENERIC_DATE_RE.search(text)
    ts = _parse_generic_date(date_match.group(1)) if date_match else None
    if ts is not None:
        confidence += 0.1

    time_match = _GENERIC_TIME_RE.search(text)
    if ts is not None and time_match:
        parsed_time = _parse_generic_time(time_match.group(1), time_match.group(2))
        if parsed_time:
            ts = ts.replace(
                hour=parsed_time[0], minute=parsed_time[1], second=parsed_time[2]
            )
            confidence += 0.05

    ref_match = _REF_RE.search(text)
    ref = ref_match.group(1) if ref_match else None
    if ref:
        confidence += 0.1

    balance_match = _BALANCE_RE.search(text)
    balance_paise = _parse_amount(balance_match.group(1)) if balance_match else None
    if balance_paise is not None:
        confidence += 0.1

    return ParsedTxn(
        amount_paise=amount,
        direction=direction,
        vpa=counterparty,
        ref=ref,
        bank_label=None,
        ts=ts,
        balance_paise=balance_paise,
        raw_text=text,
        parse_method="generic",
        confidence=min(confidence, 0.95),
    )


def parse_sms(text: str, use_llm_fallback: bool = False) -> ParsedTxn | None:
    """Parse a single bank SMS: try the 5 known bank templates first, then a
    template-free generic extractor that pulls amount/direction/counterparty/
    date/time/ref/balance independently. Returns None (not an exception)
    when neither finds enough to trust, so callers can cheaply count parse
    failures."""
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
            parse_method="template",
            confidence=1.0,
        )

    generic = _parse_generic(normalized)
    if generic is not None:
        return generic

    if use_llm_fallback:
        raise LLMFallbackNotImplemented(
            "LLM JSON-schema extraction fallback is not wired up until Phase 5"
        )
    return None
