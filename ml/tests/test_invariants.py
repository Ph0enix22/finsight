"""Hard invariants the generator must never violate: balance never negative,
balance continuity txn-to-txn, one bank per account (two for a credit-card
archetype, and only on the categories a card would actually be used for),
and no merchant outside the archetype's allow-list."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = REPO_ROOT / "data" / "sample"

_spec = importlib.util.spec_from_file_location(
    "finsight_generate", REPO_ROOT / "scripts" / "generate.py"
)
generate = importlib.util.module_from_spec(_spec)
sys.modules["finsight_generate"] = (
    generate  # dataclass() needs this registered to resolve type hints
)
_spec.loader.exec_module(generate)

PERSONA_ARCHETYPE = {"aarav": "student", "priya": "salaried", "fatima": "freelancer"}


def _load(persona: str) -> dict | None:
    path = SAMPLE_DIR / f"{persona}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


_DATA = {p: _load(p) for p in PERSONA_ARCHETYPE}
requires_data = pytest.mark.skipif(
    not all(_DATA.values()),
    reason="data/sample not generated — run scripts/generate.py",
)


@requires_data
@pytest.mark.parametrize("persona", list(PERSONA_ARCHETYPE))
def test_balance_never_negative(persona: str) -> None:
    for t in _DATA[persona]["txns"]:
        assert (
            t["balance_after_paise"] >= 0
        ), f"{persona} went negative at {t['ts']}: {t['balance_after_paise']}"


@requires_data
@pytest.mark.parametrize("persona", list(PERSONA_ARCHETYPE))
def test_balance_continuity(persona: str) -> None:
    data = _DATA[persona]
    bal = data["starting_balance_paise"]
    for t in sorted(data["txns"], key=lambda t: t["ts"]):
        bal += t["amount_paise"] if t["direction"] == "CR" else -t["amount_paise"]
        assert (
            bal == t["balance_after_paise"]
        ), f"{persona} balance diverges at {t['ts']}"
    assert bal == data["ending_balance_paise"]


@requires_data
@pytest.mark.parametrize("persona", list(PERSONA_ARCHETYPE))
def test_one_bank_per_account(persona: str) -> None:
    data = _DATA[persona]
    banks = {t["bank"] for t in data["txns"]}
    if data["secondary_bank"]:
        assert banks <= {data["bank"], data["secondary_bank"]}
        # bank is assigned from the TRUE category at commit time; label noise
        # (~3% of txns) only relabels the displayed `category` afterwards.
        off_card_categories = {
            t["true_category"]
            for t in data["txns"]
            if t["bank"] == data["secondary_bank"]
        }
        assert off_card_categories <= {"shopping", "subscriptions"}
    else:
        assert banks == {
            data["bank"]
        }, f"{persona} should use exactly one bank, saw {banks}"


@requires_data
@pytest.mark.parametrize("persona", list(PERSONA_ARCHETYPE))
def test_no_merchant_outside_allow_list(persona: str) -> None:
    archetype = generate.ARCHETYPES[PERSONA_ARCHETYPE[persona]]
    excluded = archetype.excluded_merchants
    for t in _DATA[persona]["txns"]:
        assert (
            t["merchant_key"] not in excluded
        ), f"{persona} has a disallowed merchant: {t['merchant_key']}"
