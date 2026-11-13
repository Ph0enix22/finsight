import csv
import io
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models.enums import Category, Direction, TxnSource
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.util import utcnow
from finsight_ml.categorise import categorise
from finsight_ml.normalise import normalise_merchant
from finsight_ml.parse import ParsedTxn, parse_sms


def get_or_create_merchant(
    session: Session, name: str, category: str | None
) -> Merchant | None:
    if not name:
        return None
    existing = session.exec(
        select(Merchant).where(Merchant.canonical_name == name)
    ).first()
    if existing:
        return existing
    default_category = Category(category) if category else Category.SHOPPING
    merchant = Merchant(
        canonical_name=name,
        vpa_patterns=[],
        default_category=default_category,
        logo_key=name[0].upper(),
    )
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant


def _persist(
    session: Session,
    account_id: int,
    amount_paise: int,
    direction: str,
    ts: datetime,
    raw_text: str,
    source: TxnSource,
    vpa: str,
) -> Transaction:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    normalised = normalise_merchant(vpa or raw_text)
    merchant = get_or_create_merchant(session, normalised.name, normalised.category)
    category, confidence = categorise(
        {
            "surface_name": normalised.name,
            "vpa": vpa,
            "amount_paise": amount_paise,
            "ts": ts,
        }
    )
    txn = Transaction(
        account_id=account_id,
        ts=ts,
        amount_paise=amount_paise,
        direction=Direction(direction),
        raw_text=raw_text,
        source=source,
        merchant_id=merchant.id if merchant else None,
        category=Category(category),
        category_confidence=confidence,
        is_user_labelled=False,
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


def ingest_sms(session: Session, account_id: int, raw_text: str) -> Transaction | None:
    parsed: ParsedTxn | None = parse_sms(raw_text)
    if parsed is None:
        return None
    return _persist(
        session,
        account_id,
        parsed.amount_paise,
        parsed.direction,
        parsed.ts or utcnow(),
        raw_text,
        TxnSource.SMS,
        parsed.vpa or "",
    )


def parse_statement_row(line: str) -> dict | None:
    """Parse one CSV/PDF-extracted statement row:
    Date,Narration,Debit,Credit,Balance[,Category] — tolerant of a PDF text
    dump that preserves this same comma-delimited column layout."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 5:
        return None
    date_str, narration, debit, credit = parts[0], parts[1], parts[2], parts[3]
    try:
        ts = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return None
    if debit:
        try:
            amount_paise = round(float(debit) * 100)
        except ValueError:
            return None
        direction = "DR"
    elif credit:
        try:
            amount_paise = round(float(credit) * 100)
        except ValueError:
            return None
        direction = "CR"
    else:
        return None
    vpa = ""
    if narration.upper().startswith("UPI/"):
        segs = narration.split("/")
        if len(segs) >= 4:
            vpa = segs[3]
    return {
        "ts": ts,
        "amount_paise": amount_paise,
        "direction": direction,
        "narration": narration,
        "vpa": vpa,
    }


def ingest_csv(session: Session, account_id: int, file_bytes: bytes) -> tuple[int, int]:
    text = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if rows and rows[0] and rows[0][0].strip().lower() == "date":
        rows = rows[1:]
    ingested, skipped = 0, 0
    for row in rows:
        parsed = parse_statement_row(",".join(row))
        if parsed is None:
            skipped += 1
            continue
        _persist(
            session,
            account_id,
            parsed["amount_paise"],
            parsed["direction"],
            parsed["ts"],
            parsed["narration"],
            TxnSource.CSV,
            parsed["vpa"],
        )
        ingested += 1
    return ingested, skipped


def ingest_pdf(session: Session, account_id: int, file_bytes: bytes) -> tuple[int, int]:
    import pdfplumber

    ingested, skipped = 0, 0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                parsed = parse_statement_row(line)
                if parsed is None:
                    skipped += 1
                    continue
                _persist(
                    session,
                    account_id,
                    parsed["amount_paise"],
                    parsed["direction"],
                    parsed["ts"],
                    parsed["narration"],
                    TxnSource.PDF,
                    parsed["vpa"],
                )
                ingested += 1
    return ingested, skipped
