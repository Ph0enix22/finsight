from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import engine
from app.services.ingest_service import ingest_csv, ingest_pdf, ingest_sms

router = APIRouter()


def get_session() -> Session:
    with Session(engine) as session:
        yield session


class IngestSMSRequest(BaseModel):
    account_id: int
    raw_text: str


class IngestSMSResponse(BaseModel):
    txn_id: int
    amount_paise: int
    direction: str
    category: str
    category_confidence: float
    txn_ids: list[int]


class IngestStatementResponse(BaseModel):
    ingested: int
    skipped: int


@router.post("/ingest/sms", response_model=IngestSMSResponse)
def ingest_sms_endpoint(
    payload: IngestSMSRequest, session: Session = Depends(get_session)
) -> IngestSMSResponse:
    txn = ingest_sms(session, payload.account_id, payload.raw_text)
    if txn is None:
        raise HTTPException(status_code=422, detail="Could not parse SMS text")
    return IngestSMSResponse(
        txn_id=txn.id,
        amount_paise=txn.amount_paise,
        direction=txn.direction.value,
        category=txn.category.value,
        category_confidence=txn.category_confidence or 0.0,
        txn_ids=[txn.id],
    )


@router.post("/ingest/statement", response_model=IngestStatementResponse)
async def ingest_statement_endpoint(
    account_id: int, file: UploadFile, session: Session = Depends(get_session)
) -> IngestStatementResponse:
    file_bytes = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        ingested, skipped = ingest_pdf(session, account_id, file_bytes)
    else:
        ingested, skipped = ingest_csv(session, account_id, file_bytes)
    return IngestStatementResponse(ingested=ingested, skipped=skipped)
