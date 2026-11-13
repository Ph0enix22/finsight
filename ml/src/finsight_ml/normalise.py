"""Normalise a raw bank narration / VPA into a canonical merchant name +
default category, via RapidFuzz against the merchant seed dictionary. Falls
back to the cleaned VPA as the "name" when nothing matches closely enough
(SPEC fallback row) — real local kirana QR codes genuinely aren't in anyone's
merchant dictionary, so this path is expected to fire often.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from finsight_ml.merchant_seed import MERCHANTS, MerchantSeed

MATCH_THRESHOLD = 72.0

_UPI_PREFIX_RE = re.compile(r"^UPI/(?:DR|CR)/[^/]+/", re.IGNORECASE)
_VPA_RE = re.compile(r"^[\w.\-]+@[\w.\-]+$")


def _local_part(vpa: str) -> str:
    return vpa.split("@", 1)[0]


def _clean_text(text: str) -> str:
    text = _UPI_PREFIX_RE.sub("", text)
    text = re.sub(r"[^A-Za-z0-9@.\-\s]", " ", text)
    return text.strip()


def _build_candidates() -> tuple[list[str], dict[str, MerchantSeed]]:
    candidates: list[str] = []
    mapping: dict[str, MerchantSeed] = {}
    for m in MERCHANTS:
        for cand in (m.canonical_name, *[_local_part(v) for v in m.vpa_patterns]):
            key = cand.lower()
            if key not in mapping:
                candidates.append(cand)
                mapping[cand] = m
    return candidates, mapping


_CANDIDATES, _CANDIDATE_TO_MERCHANT = _build_candidates()


@dataclass
class NormalisedMerchant:
    name: str
    category: str | None
    match_score: float
    matched: bool


def normalise_merchant(raw: str) -> NormalisedMerchant:
    """`raw` may be a bare VPA ("swiggy@ybl"), a CSV narration
    ("UPI/DR/<ref>/<vpa>/<surface>"), or free text (a parsed SMS's VPA field
    or surface name). Returns the best canonical match, or a cleaned
    fallback name with category=None if nothing matches well enough.
    """
    cleaned = _clean_text(raw)
    if not cleaned:
        return NormalisedMerchant(
            name=raw.strip(), category=None, match_score=0.0, matched=False
        )

    # A CSV narration's last "/"-segment is the surface name; prefer it plus
    # the VPA local-part as query material over the full narration string.
    parts = [p for p in cleaned.split("/") if p]
    vpa_candidates = [p for p in parts if _VPA_RE.match(p)]
    query_parts = parts[-1:] if len(parts) > 1 else parts
    if vpa_candidates:
        query_parts = [_local_part(vpa_candidates[0])] + query_parts

    best_name: str | None = None
    best_score = 0.0
    for q in query_parts:
        result = process.extractOne(q, _CANDIDATES, scorer=fuzz.WRatio)
        if result and result[1] > best_score:
            best_name, best_score = result[0], result[1]

    if best_name is not None and best_score >= MATCH_THRESHOLD:
        merchant = _CANDIDATE_TO_MERCHANT[best_name]
        return NormalisedMerchant(
            name=merchant.canonical_name,
            category=merchant.category,
            match_score=best_score,
            matched=True,
        )

    fallback_source = (
        vpa_candidates[0] if vpa_candidates else (parts[-1] if parts else cleaned)
    )
    return NormalisedMerchant(
        name=(
            _local_part(fallback_source) if "@" in fallback_source else fallback_source
        ),
        category=None,
        match_score=best_score,
        matched=False,
    )
