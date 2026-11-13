"""Synthetic transaction-history generator for FinSight demo + ML training data.

Run via the ml/ venv (it needs zero third-party deps itself, but lives next to
finsight_ml so `--help` examples below assume that cwd):

    cd ml && uv run python ../scripts/generate.py --seed 42 --users 200 --end-date 2026-11-20

Output:
  data/sample/      committed: aarav.json, priya.json, fatima.json (full demo
                    datasets used by POST /api/demo/{persona}), sms_samples.txt
                    (labeled parser fixtures), statement_samples.csv.
  data/generated/   gitignored: all 203 users' full histories, used to train +
                    evaluate the categoriser (scripts/train_categoriser.py).

Balance rule: every account's running balance is opening + sum(committed
txns), exactly, and never goes negative. A debit that would overdraw is
dropped (as a declined UPI payment would be) rather than ever patched with a
fake balancing transaction.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import zlib
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml" / "src"))

from finsight_ml.merchant_seed import (
    MERCHANT_PRICE_RANGES_RUPEES,
    MERCHANTS_BY_CATEGORY,
    merchant_price_range_paise,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
GENERATED_DIR = REPO_ROOT / "data" / "generated"

CATEGORIES = tuple(MERCHANTS_BY_CATEGORY.keys())

BANKS = ["KNB", "TCB", "SDB", "MGB", "PVB"]

FIRST_NAMES = [
    "Rahul",
    "Priya",
    "Amit",
    "Sneha",
    "Vikram",
    "Ananya",
    "Rohit",
    "Kavya",
    "Arjun",
    "Divya",
    "Karan",
    "Pooja",
    "Sanjay",
    "Neha",
    "Varun",
    "Isha",
    "Aditya",
    "Riya",
    "Siddharth",
    "Meera",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Reddy",
    "Nair",
    "Iyer",
    "Patel",
    "Singh",
    "Das",
    "Mehta",
    "Rao",
    "Kumar",
    "Joshi",
    "Chatterjee",
    "Pillai",
    "Desai",
]

MESSY_MERCHANT_MARKERS = (
    "Local",
    "Street",
    "Campus",
    "Stall",
    "Dhaba",
    "Vendor",
    "Hostel Mess",
    "Market",
)


def stable_hash(s: str) -> int:
    """A process-independent hash. Python's builtin hash() is randomised per
    process for str/bytes (PYTHONHASHSEED) unless explicitly disabled, which
    silently breaks "same seed -> byte-identical output"."""
    return zlib.crc32(s.encode("utf-8"))


def round_rupee(paise: int) -> int:
    """Round to the nearest whole rupee. 3 of the 5 bank templates render
    amounts without decimals, so every generated amount must be a clean
    multiple of 100 paise or the SMS text and the ground-truth amount used
    in test fixtures will silently disagree."""
    return round(paise / 100) * 100


def rand_person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def rand_qr_vpa(rng: random.Random) -> str:
    if rng.random() < 0.5:
        digits = "".join(rng.choices("0123456789", k=10))
        suffix = "".join(rng.choices("abcdefghijklmnopqrstuvwxyz", k=3))
        return f"paytmqr{digits}{suffix}@paytm"
    handle = "".join(
        rng.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=rng.randint(5, 8))
    )
    return f"{handle}@ybl"


def truncate_name(name: str, rng: random.Random) -> str:
    words = name.upper().split()
    joined = " ".join(words)
    if len(joined) <= 6:
        return joined
    cut = rng.randint(4, max(4, len(joined) - 1))
    return joined[:cut]


# --------------------------------------------------------------------------
# Transaction record
# --------------------------------------------------------------------------


@dataclass
class Txn:
    ts: datetime
    amount_paise: int
    direction: str  # DR or CR
    category: str
    true_category: str
    merchant_key: str
    surface_name: str
    vpa: str
    bank: str
    balance_after_paise: int
    anomaly: bool = False
    duplicate: bool = False
    price_hike: bool = False
    is_messy: bool = False
    note: str = ""
    protected: bool = False

    def to_json(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class Candidate:
    """A planned event that hasn't been balance-checked yet. Debits in here
    may still be dropped at commit time if they'd overdraw the account."""

    ts: datetime
    amount_paise: int
    direction: str
    category: str
    merchant_key: str
    surface_name: str
    vpa: str
    is_messy: bool = False
    note: str = ""
    anomaly: bool = False
    price_hike: bool = False
    protected: bool = False


# --------------------------------------------------------------------------
# Archetypes
# --------------------------------------------------------------------------


@dataclass
class Archetype:
    key: str
    starting_balance_paise: int
    daily_txn_mean: float
    weekend_multiplier: float
    category_weights: dict[str, float]
    amount_ranges: dict[str, tuple[int, int]]  # paise
    income_kind: str  # "salary" | "allowance" | "stipend"
    income_amount_paise: int
    income_day_rule: str  # "1st" | "last_working_day" | "5th"
    has_rent: bool
    rent_paise: int
    has_family_transfer: bool
    family_transfer_paise: int
    has_credit_card: bool = False
    excluded_merchants: frozenset[str] = field(default_factory=frozenset)
    subscriptions: list[tuple[str, int]] = field(
        default_factory=list
    )  # (merchant_name, paise)


# Realistic, deliberately modest amount ranges (paise) — these feed a DAILY
# random draw, so ceilings for "big ticket" categories (shopping/education/
# health) are kept small; genuinely large one-off spends come from the
# recurring engine (rent, subscriptions), not this pool.
# food_delivery and dining_cafe are kept apart on purpose (wide gap, see
# _hour_for / _pick_merchant too): delivery is a cheap solo order, dining is
# a pricier in-person sit-down meal.
DEFAULT_RANGES: dict[str, tuple[int, int]] = {
    "food_delivery": (6000, 18000),
    "dining_cafe": (15000, 60000),
    "groceries_qcommerce": (10000, 60000),
    "transport": (3000, 20000),
    "utilities_recharge": (10000, 30000),
    "shopping": (10000, 150000),
    "education": (50000, 300000),
    "health": (10000, 150000),
    "entertainment": (10000, 60000),
    "transfers_friends": (5000, 30000),
    "income": (300000, 8000000),
}

# A hostel student's budget is much tighter than a salaried/freelance one —
# cheaper ranges across the board so monthly spend tracks the ~Rs 9,000/mo
# allowance instead of blowing past it every month.
STUDENT_RANGES: dict[str, tuple[int, int]] = {
    "food_delivery": (6000, 18000),
    "dining_cafe": (12000, 35000),
    "groceries_qcommerce": (10000, 40000),
    "transport": (3000, 15000),
    "utilities_recharge": (8000, 18000),
    "shopping": (10000, 70000),
    "education": (30000, 150000),
    "health": (8000, 40000),
    "entertainment": (10000, 40000),
    "transfers_friends": (6000, 18000),
    "income": (300000, 8000000),
}

# Students: no cars (no FASTag), no premium electronics/furniture, no
# professional-grade subscriptions/courses, no baby products, no serviced
# co-living (they're in a hostel/PG, not NestAway).
STUDENT_EXCLUDED = frozenset(
    {
        "FirstCry",
        "FASTag Recharge",
        "FASTag Wallet Topup",
        "Toll Plaza",
        "Apple Store Online",
        "Croma",
        "Chroma Electronics",
        "Vijay Sales",
        "Reliance Digital",
        "IKEA",
        "Decathlon",
        "Lenskart",
        "upGrad",
        "Great Learning",
        "Coursera",
        "Adobe Creative Cloud",
        "Microsoft 365",
        "LinkedIn Premium",
        "Apple One",
        "Fortis Hospital",
        "Max Healthcare",
        "Zoomcar",
        "IndiGo Airlines",
        "Vistara",
        "Stanza Living",
        "Zolo Stays",
        "NestAway",
        "CoHo Living",
        "Nestaway Rent Pay",
        "Colive Rent Pay",
        "NoBroker Rent Pay",
        "Gold's Gym AutoPay",
        "Anytime Fitness",
        "Cult.fit Gym Membership",
    }
)

# Freelancer (design student archetype): a bit more shopping/education range
# than a hostel student, but still budget-conscious — no car, no premium gym.
FREELANCER_EXCLUDED = frozenset(
    {
        "FASTag Recharge",
        "FASTag Wallet Topup",
        "Zoomcar",
        "IndiGo Airlines",
        "Vistara",
        "Gold's Gym AutoPay",
        "Anytime Fitness",
        "Fortis Hospital",
        "Max Healthcare",
        "Stanza Living",
        "Zolo Stays",
        "NestAway",
        "CoHo Living",
        "Nestaway Rent Pay",
        "Colive Rent Pay",
    }
)

# Salaried: exclude the obviously student-only/institutional entries.
SALARIED_EXCLUDED = frozenset(
    {
        "Campus Canteen",
        "Hostel Mess Committee",
        "Campus Food Court",
        "Hostel Warden Office",
        "Coaching Institute",
        "College Fee Portal",
        "Hostel Fee Office",
        "Exam Registration Fee",
        "Library Fine",
        "Spotify Student Plan",
    }
)

ARCHETYPES = {
    "student": Archetype(
        key="student",
        starting_balance_paise=150000,
        daily_txn_mean=1.4,
        weekend_multiplier=1.25,
        category_weights={
            "food_delivery": 0.36,
            "dining_cafe": 0.06,
            "groceries_qcommerce": 0.08,
            "transport": 0.14,
            "utilities_recharge": 0.03,
            "shopping": 0.08,
            "education": 0.01,
            "health": 0.02,
            "entertainment": 0.06,
            "transfers_friends": 0.03,
        },
        amount_ranges=STUDENT_RANGES,
        income_kind="allowance",
        income_amount_paise=900000,
        income_day_rule="1st",
        has_rent=False,
        rent_paise=0,
        has_family_transfer=False,
        family_transfer_paise=0,
        has_credit_card=False,
        excluded_merchants=STUDENT_EXCLUDED,
        subscriptions=[("Spotify Student Plan", 11900)],
    ),
    "salaried": Archetype(
        key="salaried",
        starting_balance_paise=1500000,
        daily_txn_mean=0.75,
        weekend_multiplier=1.4,
        category_weights={
            "food_delivery": 0.16,
            "dining_cafe": 0.13,
            "groceries_qcommerce": 0.16,
            "transport": 0.14,
            "utilities_recharge": 0.05,
            "shopping": 0.16,
            "health": 0.05,
            "entertainment": 0.11,
            "transfers_friends": 0.04,
        },
        amount_ranges=DEFAULT_RANGES,
        income_kind="salary",
        income_amount_paise=6800000,
        income_day_rule="last_working_day",
        has_rent=True,
        rent_paise=1800000,
        has_family_transfer=True,
        family_transfer_paise=800000,
        has_credit_card=True,
        excluded_merchants=SALARIED_EXCLUDED,
        subscriptions=[
            ("Netflix", 19900),
            ("Spotify", 11900),
            ("Prime Video", 33000),
            ("Gold's Gym AutoPay", 129900),
        ],
    ),
    "freelancer": Archetype(
        key="freelancer",
        starting_balance_paise=250000,
        daily_txn_mean=0.8,
        weekend_multiplier=1.2,
        category_weights={
            "food_delivery": 0.20,
            "dining_cafe": 0.10,
            "groceries_qcommerce": 0.15,
            "transport": 0.10,
            "utilities_recharge": 0.05,
            "shopping": 0.15,
            "education": 0.05,
            "health": 0.04,
            "entertainment": 0.08,
            "transfers_friends": 0.03,
        },
        amount_ranges=DEFAULT_RANGES,
        income_kind="stipend",
        income_amount_paise=600000,
        income_day_rule="5th",
        has_rent=False,
        rent_paise=0,
        has_family_transfer=False,
        family_transfer_paise=0,
        has_credit_card=False,
        excluded_merchants=FREELANCER_EXCLUDED,
        subscriptions=[("Canva", 50000)],
    ),
}

ARCHETYPE_MIX = [("student", 0.35), ("salaried", 0.40), ("freelancer", 0.25)]


# --------------------------------------------------------------------------
# Per-user generator
# --------------------------------------------------------------------------


class UserGenerator:
    def __init__(
        self,
        user_key: str,
        archetype: Archetype,
        rng: random.Random,
        start: date,
        end: date,
    ):
        self.user_key = user_key
        self.archetype = archetype
        self.rng = rng
        self.start = start
        self.end = end
        self.txns: list[Txn] = []
        self.declined_count = 0
        self.diwali_week = (date(2026, 11, 3), date(2026, 11, 10))
        self.contacts = self._make_contacts()
        self.bank = rng.choice(BANKS)
        self.secondary_bank = None
        if archetype.has_credit_card:
            self.secondary_bank = rng.choice([b for b in BANKS if b != self.bank])

    def _make_contacts(self) -> dict[str, list[tuple[str, str]]]:
        rng = self.rng
        family = [
            (rand_person_name(rng), f"{rng.randint(6000000000, 9999999999)}@upi")
            for _ in range(2)
        ]
        friends = [
            (rand_person_name(rng), f"{rng.randint(6000000000, 9999999999)}@upi")
            for _ in range(rng.randint(2, 4))
        ]
        return {"transfers_family": family, "transfers_friends": friends}

    def _bank_for(self, category: str) -> str:
        if self.secondary_bank and category in ("shopping", "subscriptions"):
            return self.secondary_bank
        return self.bank

    # -- helpers -----------------------------------------------------------

    def _pick_merchant(self, category: str) -> tuple[str, str, str, bool]:
        """Returns (merchant_key, surface_name, vpa, is_messy)."""
        rng = self.rng
        if category in ("transfers_family", "transfers_friends"):
            name, vpa = rng.choice(self.contacts[category])
            return name, name, vpa, False
        pool = [
            m
            for m in MERCHANTS_BY_CATEGORY[category]
            if m.canonical_name not in self.archetype.excluded_merchants
        ]
        if not pool:
            pool = MERCHANTS_BY_CATEGORY[category]
        if not pool:
            return category, category, rand_qr_vpa(rng), True
        m = rng.choice(pool)
        is_messy = any(marker in m.canonical_name for marker in MESSY_MERCHANT_MARKERS)
        # dining_cafe is paid in person at a QR code at the counter, not
        # through a branded delivery app — that's the realistic signal that
        # separates it from food_delivery in the raw text/VPA.
        if category == "dining_cafe" or is_messy:
            vpa = rand_qr_vpa(rng)
        else:
            vpa = rng.choice(m.vpa_patterns)
        return m.canonical_name, m.canonical_name, vpa, is_messy

    def _amount_for(self, category: str, merchant_key: str | None = None) -> int:
        category_range = self.archetype.amount_ranges[category]
        lo, hi = (
            merchant_price_range_paise(merchant_key, category_range)
            if merchant_key
            else category_range
        )
        return round_rupee(self.rng.randint(lo, hi))

    def _hour_for(self, category: str) -> int:
        rng = self.rng
        buckets = {
            # Sharp lunch/dinner/late-night delivery peaks only.
            "food_delivery": [13, 20, 21, 22],
            # In-person dining: breakfast/brunch/tea-time, daytime — no
            # overlap at all with food_delivery's hours.
            "dining_cafe": [8, 9, 10, 15, 16, 17],
            "groceries_qcommerce": [10, 18, 19],
            "transport": [8, 9, 18, 19],
            "entertainment": [19, 20, 21],
            "shopping": [12, 15, 20, 21],
        }
        if category in buckets:
            return rng.choice(buckets[category])
        return rng.randint(9, 22)

    def _make_candidate(
        self,
        ts: datetime,
        amount_paise: int,
        direction: str,
        category: str,
        merchant_key: str,
        surface_name: str,
        vpa: str,
        is_messy: bool = False,
        note: str = "",
    ) -> Candidate:
        return Candidate(
            ts=ts,
            amount_paise=amount_paise,
            direction=direction,
            category=category,
            merchant_key=merchant_key,
            surface_name=surface_name,
            vpa=vpa,
            is_messy=is_messy,
            note=note,
        )

    # -- recurring series (produces candidates, does not commit) -----------

    def _last_working_day(self, year: int, month: int) -> date:
        if month == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month + 1, 1)
        d = nxt - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    def build_recurring_candidates(self) -> list[Candidate]:
        a = self.archetype
        rng = self.rng
        out: list[Candidate] = []
        months = []
        cur = date(self.start.year, self.start.month, 1)
        while cur <= self.end:
            months.append(cur)
            cur = (
                date(cur.year + 1, 1, 1)
                if cur.month == 12
                else date(cur.year, cur.month + 1, 1)
            )

        for m in months:
            if a.income_day_rule == "1st":
                d = date(m.year, m.month, 1)
            elif a.income_day_rule == "5th":
                d = date(m.year, m.month, 5)
            else:
                d = self._last_working_day(m.year, m.month)
            if self.start <= d <= self.end:
                name = {
                    "salary": "Employer Payroll",
                    "allowance": "Parent Allowance Credit",
                    "stipend": "Stipend Credit",
                }[a.income_kind]
                vpa = next(
                    mm.vpa_patterns[0]
                    for mm in MERCHANTS_BY_CATEGORY["income"]
                    if mm.canonical_name == name
                )
                ts = datetime(
                    d.year, d.month, d.day, rng.choice([9, 10]), rng.randint(0, 59)
                )
                out.append(
                    self._make_candidate(
                        ts, a.income_amount_paise, "CR", "income", name, name, vpa
                    )
                )

            if a.has_rent:
                d = date(m.year, m.month, rng.randint(3, 5))
                if self.start <= d <= self.end:
                    key, name, vpa, _ = self._pick_merchant("rent_housing")
                    ts = datetime(
                        d.year,
                        d.month,
                        d.day,
                        rng.choice([8, 9, 10]),
                        rng.randint(0, 59),
                    )
                    out.append(
                        self._make_candidate(
                            ts, a.rent_paise, "DR", "rent_housing", key, name, vpa
                        )
                    )

            if a.has_family_transfer:
                d = date(m.year, m.month, rng.randint(1, 7))
                if self.start <= d <= self.end:
                    name, vpa = self.contacts["transfers_family"][0]
                    ts = datetime(
                        d.year, d.month, d.day, rng.randint(9, 21), rng.randint(0, 59)
                    )
                    out.append(
                        self._make_candidate(
                            ts,
                            a.family_transfer_paise,
                            "DR",
                            "transfers_family",
                            name,
                            name,
                            vpa,
                        )
                    )

            for sub_name, sub_amount in a.subscriptions:
                day = (stable_hash(f"{self.user_key}:{sub_name}") % 26) + 1
                d = date(m.year, m.month, min(day, 28))
                if self.start <= d <= self.end:
                    vpa = next(
                        mm.vpa_patterns[0]
                        for mm in MERCHANTS_BY_CATEGORY["subscriptions"]
                        if mm.canonical_name == sub_name
                    )
                    ts = datetime(
                        d.year, d.month, d.day, rng.randint(6, 23), rng.randint(0, 59)
                    )
                    out.append(
                        self._make_candidate(
                            ts,
                            sub_amount,
                            "DR",
                            "subscriptions",
                            sub_name,
                            sub_name,
                            vpa,
                        )
                    )

        if a.key == "student":
            out += self._weekly_pattern_candidates(
                "Friend Split Payment", "transfers_friends", 8000, 15000
            )
            out += self._periodic_recharge_candidates("Jio Recharge", 28)
        if a.key == "freelancer":
            out += self._freelance_credit_candidates()
        return out

    def _weekly_pattern_candidates(
        self, merchant_name: str, category: str, lo: int, hi: int
    ) -> list[Candidate]:
        rng = self.rng
        out = []
        d = self.start + timedelta(days=rng.randint(0, 6))
        while d <= self.end:
            name, vpa = rng.choice(
                self.contacts.get(category, self.contacts["transfers_friends"])
            )
            amount = round_rupee(rng.randint(lo, hi))
            ts = datetime(
                d.year, d.month, d.day, rng.randint(19, 22), rng.randint(0, 59)
            )
            out.append(
                self._make_candidate(
                    ts, amount, "DR", category, name, name, vpa, note=merchant_name
                )
            )
            d += timedelta(days=7)
        return out

    def _periodic_recharge_candidates(
        self, merchant_name: str, period_days: int
    ) -> list[Candidate]:
        rng = self.rng
        out = []
        pool = MERCHANTS_BY_CATEGORY["utilities_recharge"]
        merchant = next((m for m in pool if m.canonical_name == merchant_name), pool[0])
        d = self.start + timedelta(days=rng.randint(0, period_days - 1))
        while d <= self.end:
            vpa = rng.choice(merchant.vpa_patterns)
            amount = round_rupee(rng.randint(19900, 29900))
            ts = datetime(
                d.year, d.month, d.day, rng.randint(8, 20), rng.randint(0, 59)
            )
            out.append(
                self._make_candidate(
                    ts,
                    amount,
                    "DR",
                    "utilities_recharge",
                    merchant.canonical_name,
                    merchant.canonical_name,
                    vpa,
                )
            )
            d += timedelta(days=period_days)
        return out

    def _freelance_credit_candidates(self) -> list[Candidate]:
        rng = self.rng
        out = []
        cur = date(self.start.year, self.start.month, 1)
        while cur <= self.end:
            n = rng.randint(2, 4)
            for _ in range(n):
                day = rng.randint(1, 28)
                d = date(cur.year, cur.month, day)
                if self.start <= d <= self.end:
                    amount = round_rupee(rng.randint(300000, 1500000))
                    ts = datetime(
                        d.year, d.month, d.day, rng.randint(9, 21), rng.randint(0, 59)
                    )
                    vpa = next(
                        mm.vpa_patterns[0]
                        for mm in MERCHANTS_BY_CATEGORY["income"]
                        if mm.canonical_name == "Freelance Client Payment"
                    )
                    out.append(
                        self._make_candidate(
                            ts,
                            amount,
                            "CR",
                            "income",
                            "Freelance Client Payment",
                            "Freelance Client Payment",
                            vpa,
                        )
                    )
            cur = (
                date(cur.year + 1, 1, 1)
                if cur.month == 12
                else date(cur.year, cur.month + 1, 1)
            )
        return out

    # -- daily discretionary spend (produces candidates) --------------------

    def build_discretionary_candidates(self) -> list[Candidate]:
        rng = self.rng
        a = self.archetype
        out: list[Candidate] = []
        d = self.start
        while d <= self.end:
            mean = a.daily_txn_mean
            if d.weekday() >= 5:
                mean *= a.weekend_multiplier
            if self.diwali_week[0] <= d <= self.diwali_week[1]:
                mean *= 1.5
            if d.day >= 25:
                mean *= 0.6  # month-end tightening

            n = max(0, round(rng.gauss(mean, 0.6)))
            for _ in range(n):
                cats = list(a.category_weights.keys())
                weights = list(a.category_weights.values())
                category = rng.choices(cats, weights=weights, k=1)[0]
                key, name, vpa, messy = self._pick_merchant(category)
                amount = self._amount_for(category, merchant_key=key)
                if self.diwali_week[0] <= d <= self.diwali_week[1] and category in (
                    "shopping",
                    "entertainment",
                ):
                    amount = round_rupee(int(amount * rng.uniform(1.2, 1.6)))
                hour = self._hour_for(category)
                ts = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59))
                out.append(
                    self._make_candidate(
                        ts, amount, "DR", category, key, name, vpa, is_messy=messy
                    )
                )
            d += timedelta(days=1)
        return out

    # -- label injection (operates on candidates, before commit) ------------

    def inject_anomalies_and_duplicates(
        self,
        candidates: list[Candidate],
        anomaly_rate: float = 0.02,
        duplicate_rate: float = 0.01,
    ) -> list[Candidate]:
        rng = self.rng
        debit_idx = [i for i, c in enumerate(candidates) if c.direction == "DR"]
        n_anom = max(0, round(len(debit_idx) * anomaly_rate))
        for i in rng.sample(debit_idx, min(n_anom, len(debit_idx))):
            c = candidates[i]
            c.amount_paise = round_rupee(int(c.amount_paise * rng.uniform(3, 8)))
            c.anomaly = True
        n_dup = max(0, round(len(debit_idx) * duplicate_rate))
        extra = []
        for i in rng.sample(debit_idx, min(n_dup, len(debit_idx))):
            c = candidates[i]
            dup = Candidate(
                ts=c.ts + timedelta(minutes=rng.randint(1, 10)),
                amount_paise=c.amount_paise,
                direction=c.direction,
                category=c.category,
                merchant_key=c.merchant_key,
                surface_name=c.surface_name,
                vpa=c.vpa,
                is_messy=c.is_messy,
                anomaly=c.anomaly,  # if the original got anomaly-inflated, the clone's amount is too
            )
            extra.append(dup)
        return candidates + extra

    def apply_label_noise(self, rate: float = 0.03) -> None:
        """Flips ~rate of categories to simulate imperfect real-world
        labelling — but never on a `protected` txn (scripted story beats
        like aarav's 41 food payments or priya's gym hike need their exact
        category preserved, or the demo narrative silently breaks)."""
        rng = self.rng
        eligible = [i for i, t in enumerate(self.txns) if not t.protected]
        n = max(0, round(len(eligible) * rate))
        for i in rng.sample(eligible, min(n, len(eligible))):
            t = self.txns[i]
            others = [c for c in CATEGORIES if c != t.category]
            t.category = rng.choice(others)

    # -- commit: strict chronological balance walk, drop overdrafts --------

    def dry_run_balance(self, candidates: list[Candidate], start_balance: int) -> int:
        """Same decline rule as commit(), but doesn't record anything — used
        to size a scripted budget against a projected balance before the
        real (single, chronologically-ordered) commit happens."""
        return self.dry_run_preview(candidates, start_balance)[0]

    def dry_run_preview(
        self, candidates: list[Candidate], start_balance: int
    ) -> tuple[int, list[Candidate]]:
        """Like dry_run_balance, but also returns which candidates would be
        declined — used to check that a scripted set (a fixed story-beat
        count) survives the decline rule before committing for real."""
        bal = start_balance
        declined = []
        for c in sorted(candidates, key=lambda c: c.ts):
            if c.direction == "DR":
                if bal - c.amount_paise < 0:
                    declined.append(c)
                    continue
                bal -= c.amount_paise
            else:
                bal += c.amount_paise
        return bal, declined

    def commit(self, candidates: list[Candidate], start_balance: int) -> int:
        """Applies candidates in timestamp order starting from start_balance.
        A debit that would overdraw is dropped (declined), never recorded.
        Returns the ending balance.

        Must be called with ALL candidates for a given time window in one
        go — committing the same window in multiple separate calls would
        process them in call-order, not true chronological order, and the
        stored balance_after_paise would stop matching a strict walk of the
        final (ts-sorted) transaction list."""
        bal = start_balance
        for c in sorted(candidates, key=lambda c: c.ts):
            if c.direction == "DR":
                if bal - c.amount_paise < 0:
                    self.declined_count += 1
                    continue
                bal -= c.amount_paise
            else:
                bal += c.amount_paise
            self.txns.append(
                Txn(
                    ts=c.ts,
                    amount_paise=c.amount_paise,
                    direction=c.direction,
                    category=c.category,
                    true_category=c.category,
                    merchant_key=c.merchant_key,
                    surface_name=c.surface_name,
                    vpa=c.vpa,
                    bank=self._bank_for(c.category),
                    balance_after_paise=bal,
                    anomaly=c.anomaly,
                    price_hike=c.price_hike,
                    is_messy=c.is_messy,
                    note=c.note,
                    protected=c.protected,
                )
            )
        return bal

    def sort(self) -> None:
        self.txns.sort(key=lambda t: t.ts)

    def balance_at_end_of(self, d: date) -> int:
        in_range = [t for t in self.txns if t.ts.date() <= d]
        if not in_range:
            return self.archetype.starting_balance_paise
        return max(in_range, key=lambda t: t.ts).balance_after_paise

    def month_summary(self) -> list[dict]:
        """Month-by-month (inflow, outflow, closing balance)."""
        by_month: dict[str, dict] = {}
        for t in sorted(self.txns, key=lambda t: t.ts):
            key = t.ts.strftime("%Y-%m")
            m = by_month.setdefault(
                key,
                {
                    "month": key,
                    "inflow_paise": 0,
                    "outflow_paise": 0,
                    "closing_balance_paise": 0,
                },
            )
            if t.direction == "CR":
                m["inflow_paise"] += t.amount_paise
            else:
                m["outflow_paise"] += t.amount_paise
            m["closing_balance_paise"] = t.balance_after_paise
        return list(by_month.values())


# --------------------------------------------------------------------------
# Scripted persona story beats — planned as a spend BUDGET against the real
# simulated cash position, never as a plug transaction after the fact.
# --------------------------------------------------------------------------


def build_aarav(
    user_key: str, archetype_key: str, seed: int, start: date, end: date, as_of: date
) -> UserGenerator:
    rng = random.Random(f"{seed}:{user_key}")
    gen = UserGenerator(user_key, ARCHETYPES[archetype_key], rng, start, end)

    month_start = date(as_of.year, as_of.month, 1)

    all_recurring = gen.build_recurring_candidates()
    all_discretionary = gen.build_discretionary_candidates()
    candidates = all_recurring + all_discretionary
    candidates = gen.inject_anomalies_and_duplicates(candidates)

    # Phase 1: everything strictly before this month, committed normally.
    before = [c for c in candidates if c.ts.date() < month_start]
    balance_before_month = gen.commit(before, gen.archetype.starting_balance_paise)

    # Phase 2: this month's recurring items up to as_of (allowance, Jio
    # recharge/hostel split if due) — still normal, no scripting yet. Not
    # committed yet — just a dry-run balance to size the scripted budget,
    # since phase 2 and phase 3 land in the same window and must be
    # committed together in true chronological order (see commit()'s
    # docstring on why splitting an overlapping window breaks continuity).
    this_month_recurring = [
        c
        for c in candidates
        if month_start <= c.ts.date() <= as_of
        and c.category not in ("food_delivery", "dining_cafe")
        and not c.anomaly
    ]
    balance_after_recurring = gen.dry_run_balance(
        this_month_recurring, balance_before_month
    )

    # Phase 3: the scripted beats, SIZED to the budget that's actually there
    # — not patched in afterwards. Anomaly first (fixed amount, the story
    # beat), then food gets whatever's left down to a sane floor/ceiling.
    anomaly_amount = 249900
    target_end_balance = 310000
    food_total = balance_after_recurring - anomaly_amount - target_end_balance
    food_total = max(1500 * 100, min(food_total, 6000 * 100))
    food_total = round_rupee(food_total)

    days_span = (as_of - month_start).days + 1
    n_food = 41

    # Only merchants whose own minimum price actually fits under Rs 200 — a
    # broke hostel student eating 41 cheap meals over two weeks wouldn't be
    # hitting Barbeque Nation or Starbucks anyway, and forcing a premium
    # merchant's price down to fit the beat would violate its own range.
    def _fits_under_200(m: object) -> bool:
        lo, _ = MERCHANT_PRICE_RANGES_RUPEES.get(m.canonical_name, (0, 999))
        return lo < 150

    pool = [m for m in MERCHANTS_BY_CATEGORY["food_delivery"] if _fits_under_200(m)] + [
        m
        for m in MERCHANTS_BY_CATEGORY["dining_cafe"]
        if m.canonical_name not in gen.archetype.excluded_merchants
        and _fits_under_200(m)
    ]
    anomaly_day = month_start + timedelta(days=min(6, days_span - 1))
    anomaly_ts = datetime(anomaly_day.year, anomaly_day.month, anomaly_day.day, 2, 13)

    def build_scripted(total_paise: int) -> list[Candidate]:
        # Each payment is drawn from ITS OWN merchant's realistic price band
        # (a chai isn't the same price as a Pizza Hut order), biased slot by
        # slot toward whatever's left of the budget — not a fixed total
        # split evenly across arbitrary amounts. The achieved sum is
        # whatever this plan yields, not forced to a figure.
        out = []
        remaining = total_paise
        for slot in range(n_food):
            slots_left = n_food - slot
            d = month_start + timedelta(days=rng.randint(0, days_span - 1))
            m = rng.choice(pool)
            is_messy = any(
                marker in m.canonical_name for marker in MESSY_MERCHANT_MARKERS
            )
            vpa = (
                rand_qr_vpa(rng)
                if (is_messy or m.category == "dining_cafe")
                else rng.choice(m.vpa_patterns)
            )
            lo, hi = merchant_price_range_paise(m.canonical_name, (2000, 19900))
            hi = min(hi, 19900)  # keep the "<Rs 200 per payment" story beat
            lo = min(lo, hi)
            if slots_left > 1:
                target = remaining / slots_left
                jitter = rng.uniform(-0.25, 0.25) * (hi - lo)
                amount = round_rupee(int(max(lo, min(hi, target + jitter))))
            else:
                amount = round_rupee(int(max(lo, min(hi, remaining))))
            remaining -= amount

            hour = rng.choice([8, 12, 13, 14, 19, 20, 21, 22])
            ts = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59))
            out.append(
                Candidate(
                    ts=ts,
                    amount_paise=amount,
                    direction="DR",
                    category=m.category,
                    merchant_key=m.canonical_name,
                    surface_name=m.canonical_name,
                    vpa=vpa,
                    is_messy=is_messy,
                    protected=True,
                )
            )
        out.append(
            Candidate(
                ts=anomaly_ts,
                amount_paise=anomaly_amount,
                direction="DR",
                category="shopping",
                merchant_key="QuickFix Mobile Repair Kiosk",
                surface_name="QuickFix Mobile Repair Kiosk",
                vpa=rand_qr_vpa(rng),
                is_messy=False,
                anomaly=True,
                note="scripted story-beat anomaly",
                protected=True,
            )
        )
        return out

    # The exact 41-payment, one-anomaly count is the story beat — if sizing
    # the budget this tight means one of them would transiently overdraw
    # mid-month (even though the month-end total works out), shrink the
    # food budget and re-plan rather than let the count silently drop.
    scripted = build_scripted(food_total)
    for _ in range(6):
        _, declined = gen.dry_run_preview(
            this_month_recurring + scripted, balance_before_month
        )
        if not declined:
            break
        food_total = round_rupee(int(food_total * 0.85))
        scripted = build_scripted(food_total)

    balance_end_of_as_of = gen.commit(
        this_month_recurring + scripted, balance_before_month
    )

    # Phase 4: the rest of the window (post as_of), normal simulation.
    after = [c for c in candidates if c.ts.date() > as_of]
    gen.commit(after, balance_end_of_as_of)

    gen.apply_label_noise()
    gen.sort()
    return gen


def build_priya(
    user_key: str, archetype_key: str, seed: int, start: date, end: date, as_of: date
) -> UserGenerator:
    rng = random.Random(f"{seed}:{user_key}")
    gen = UserGenerator(user_key, ARCHETYPES[archetype_key], rng, start, end)

    candidates = gen.build_recurring_candidates() + gen.build_discretionary_candidates()
    candidates = gen.inject_anomalies_and_duplicates(candidates)

    month_start = date(as_of.year, as_of.month, 1)
    month_end = (
        date(as_of.year + 1, 1, 1) - timedelta(days=1)
        if as_of.month == 12
        else date(as_of.year, as_of.month + 1, 1) - timedelta(days=1)
    )
    hiked = False
    for c in candidates:
        if (
            c.merchant_key == "Gold's Gym AutoPay"
            and month_start <= c.ts.date() <= month_end
        ):
            c.amount_paise = 159900
            c.price_hike = True
            c.protected = True
            hiked = True
    if not hiked:
        # The hash-chosen billing day for this subscription falls after the
        # window's end (common for a partial final month) — the hike is a
        # named story beat, so schedule it explicitly rather than let it
        # silently not happen this month.
        d = date(as_of.year, as_of.month, min(10, as_of.day))
        ts = datetime(d.year, d.month, d.day, rng.randint(6, 23), rng.randint(0, 59))
        vpa = next(
            mm.vpa_patterns[0]
            for mm in MERCHANTS_BY_CATEGORY["subscriptions"]
            if mm.canonical_name == "Gold's Gym AutoPay"
        )
        candidates.append(
            Candidate(
                ts=ts,
                amount_paise=159900,
                direction="DR",
                category="subscriptions",
                merchant_key="Gold's Gym AutoPay",
                surface_name="Gold's Gym AutoPay",
                vpa=vpa,
                price_hike=True,
                protected=True,
            )
        )

    gen.commit(candidates, gen.archetype.starting_balance_paise)
    gen.apply_label_noise()
    gen.sort()
    return gen


def build_generic_user(
    user_key: str, archetype_key: str, seed: int, start: date, end: date
) -> UserGenerator:
    rng = random.Random(f"{seed}:{user_key}")
    gen = UserGenerator(user_key, ARCHETYPES[archetype_key], rng, start, end)
    candidates = gen.build_recurring_candidates() + gen.build_discretionary_candidates()
    candidates = gen.inject_anomalies_and_duplicates(candidates)
    gen.commit(candidates, gen.archetype.starting_balance_paise)
    gen.apply_label_noise()
    gen.sort()
    return gen


# --------------------------------------------------------------------------
# Rendering: Txn -> SMS text (5 fictional banks) and CSV narration rows
# --------------------------------------------------------------------------


def amt_str(paise: int, decimals: bool = True) -> str:
    rupees = paise / 100
    return f"{rupees:,.2f}" if decimals else f"{round(rupees)}"


def rand_ref(rng: random.Random, prefix: str = "") -> str:
    return prefix + "".join(rng.choices("0123456789", k=10))


def acct_suffix(user_key: str) -> str:
    return str(stable_hash(user_key) % 9000 + 1000)


def render_knb(t: Txn, acct: str, rng: random.Random) -> str:
    verb, prep = ("debited", "to") if t.direction == "DR" else ("credited", "from")
    moved = "from" if t.direction == "DR" else "to"
    return (
        f"Dear Customer, Rs.{amt_str(t.amount_paise)} {verb} {moved} a/c XX{acct} on "
        f"{t.ts.strftime('%d-%b-%y')} {t.ts.strftime('%H:%M')} {prep} VPA {t.vpa}. "
        f"Ref No {rand_ref(rng)}. Avl Bal Rs.{amt_str(t.balance_after_paise)}. -KNB"
    )


def render_tcb(t: Txn, acct: str, rng: random.Random) -> str:
    verb = "sent" if t.direction == "DR" else "received"
    prep = "to" if t.direction == "DR" else "from"
    return (
        f"TCB Alert: You have {verb} Rs {amt_str(t.amount_paise, decimals=False)} {prep} {t.vpa} on "
        f"{t.ts.strftime('%d-%b-%y')} at {t.ts.strftime('%H:%M:%S')} via UPI. "
        f"Txn Ref {rand_ref(rng, 'TCB')}. Bal: Rs {amt_str(t.balance_after_paise, decimals=False)}"
    )


def render_sdb(t: Txn, acct: str, rng: random.Random) -> str:
    verb = "paid to" if t.direction == "DR" else "received from"
    return (
        f"SDB: INR {amt_str(t.amount_paise)} {verb} {t.vpa} UPI Ref {rand_ref(rng, 'SDB')} on "
        f"{t.ts.strftime('%d-%b-%y')} {t.ts.strftime('%H:%M')}. Available balance INR {amt_str(t.balance_after_paise)}"
    )


def render_mgb(t: Txn, acct: str, rng: random.Random) -> str:
    verb, prep = (
        ("debited frm", "to") if t.direction == "DR" else ("credited to", "from")
    )
    return (
        f"MGB-UPI: ₹{amt_str(t.amount_paise, decimals=False)} {verb} a/c {acct} {prep} {t.vpa} on "
        f"{t.ts.strftime('%d-%b-%y')}, {t.ts.strftime('%H:%M:%S')} hrs. RRN {rand_ref(rng, 'MGB')}. "
        f"Bal ₹{amt_str(t.balance_after_paise, decimals=False)}"
    )


def render_pvb(t: Txn, acct: str, rng: random.Random) -> str:
    verb = "dr" if t.direction == "DR" else "cr"
    return (
        f"PVB: Rs{amt_str(t.amount_paise, decimals=False)} {verb} for UPI/{rand_ref(rng, 'PVB')}/{t.vpa} on "
        f"{t.ts.strftime('%d-%b-%y')}. Bal Rs{amt_str(t.balance_after_paise, decimals=False)}"
    )


_RENDERERS = {
    "KNB": render_knb,
    "TCB": render_tcb,
    "SDB": render_sdb,
    "MGB": render_mgb,
    "PVB": render_pvb,
}

_PROMO_SUFFIXES = [
    " Download our app for exclusive offers!",
    " T&C apply. Visit nearest branch for details.",
    " Your feedback matters - rate us on the app store.",
    " Stay safe - never share your UPI PIN with anyone.",
]


def apply_noise(sms: str, rng: random.Random) -> str:
    out = sms
    r = rng.random()
    if r < 0.15:
        out = out.replace("Rs.", "INR ").replace("Rs ", "INR ").replace("₹", "INR ")
    elif r < 0.30:
        out = out.replace("Rs.", "₹").replace("Rs ", "₹")
    if rng.random() < 0.25:
        out = re_sub_amount_comma(out, rng)
    if rng.random() < 0.15:
        words = out.split(" ")
        if len(words) > 6:
            cut = rng.randint(3, len(words) - 3)
            out = " ".join(words[:cut]) + "\n" + " ".join(words[cut:])
    if rng.random() < 0.15:
        for marker in ("Avl Bal", "Bal:", "Available balance", "Bal ₹", "Bal Rs"):
            idx = out.find(marker)
            if idx != -1:
                out = out[:idx].rstrip(". ")
                break
    if rng.random() < 0.25:
        out += rng.choice(_PROMO_SUFFIXES)
    return out


def re_sub_amount_comma(text: str, rng: random.Random) -> str:
    """Add a thousands comma to the AMOUNT only (right after the currency
    symbol) — never touch digits inside a VPA/ref, which is what a naive
    text-wide digit regex would otherwise corrupt."""

    def add_comma(m: re.Match[str]) -> str:
        digits = m.group(2)
        if len(digits) <= 3:
            return m.group(0)
        return f"{m.group(1)}{digits[:-3]},{digits[-3:]}"

    return re.sub(r"((?:Rs\.?|INR|₹)\s*)(\d{4,})(?!\.\d)", add_comma, text, count=1)


_UNPARSEABLE_TEMPLATES = [
    "Your OTP for login is {otp}. Valid for 10 mins. Do not share with anyone.",
    "Dear Customer, your card ending {last4} will expire this month. Please renew.",
    "Reminder: Your EMI payment is due in 3 days. Avoid late fees.",
    "Congratulations! You have been selected for a special offer. Click here to claim.",
    "Thank you for banking with us. Have a great day!",
]


def make_unparseable(rng: random.Random) -> str:
    tpl = rng.choice(_UNPARSEABLE_TEMPLATES)
    return tpl.format(otp=rng.randint(100000, 999999), last4=rng.randint(1000, 9999))


def render_sms(
    t: Txn, user_key: str, rng: random.Random, unparseable: bool = False
) -> str:
    if unparseable:
        return make_unparseable(rng)
    acct = acct_suffix(user_key)
    sms = _RENDERERS[t.bank](t, acct, rng)
    return apply_noise(sms, rng)


def render_csv_narration(t: Txn, rng: random.Random) -> str:
    surface = (
        truncate_name(t.surface_name, rng)
        if rng.random() < 0.2
        else t.surface_name.upper()
    )
    ref = rand_ref(rng)
    return f"UPI/{t.direction}/{ref}/{t.vpa}/{surface}"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def pick_archetype(rng: random.Random) -> str:
    keys = [k for k, _ in ARCHETYPE_MIX]
    weights = [w for _, w in ARCHETYPE_MIX]
    return rng.choices(keys, weights=weights, k=1)[0]


def txn_sample_dict(t: Txn) -> dict:
    return {
        "ts": t.ts.isoformat(),
        "amount_paise": t.amount_paise,
        "direction": t.direction,
        "category": t.category,
        "true_category": t.true_category,
        "merchant_key": t.merchant_key,
        "surface_name": t.surface_name,
        "vpa": t.vpa,
        "bank": t.bank,
        "balance_after_paise": t.balance_after_paise,
        "anomaly": t.anomaly,
        "duplicate": t.duplicate,
        "price_hike": t.price_hike,
        "is_messy": t.is_messy,
        "note": t.note,
    }


def write_user_json(gen: UserGenerator, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "user_key": gen.user_key,
        "archetype": gen.archetype.key,
        "bank": gen.bank,
        "secondary_bank": gen.secondary_bank,
        "starting_balance_paise": gen.archetype.starting_balance_paise,
        "ending_balance_paise": (
            gen.txns[-1].balance_after_paise
            if gen.txns
            else gen.archetype.starting_balance_paise
        ),
        "declined_count": gen.declined_count,
        "txns": [txn_sample_dict(t) for t in gen.txns],
    }
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def build_sms_samples(
    persona_gens: dict[str, UserGenerator], rng: random.Random, n: int = 180
) -> list[dict]:
    pool: list[tuple[Txn, str]] = []
    for key, gen in persona_gens.items():
        for t in gen.txns:
            pool.append((t, key))
    rng.shuffle(pool)
    pool = pool[:n]

    samples = []
    for t, user_key in pool:
        unparseable = rng.random() < 0.05
        sms = render_sms(t, user_key, rng, unparseable=unparseable)
        if unparseable:
            samples.append({"sms": sms, "expected": None})
        else:
            samples.append(
                {
                    "sms": sms,
                    "expected": {
                        "amount_paise": t.amount_paise,
                        "direction": t.direction,
                        "vpa": t.vpa,
                        "bank": t.bank,
                    },
                }
            )
    return samples


def print_report_preview(gen: UserGenerator, rng: random.Random) -> None:
    debit_txns = [t for t in gen.txns if t.direction in ("DR", "CR")]
    sample = rng.sample(debit_txns, min(15, len(debit_txns)))
    print("\n--- 15 random SMS lines (aarav) ---")
    for t in sample:
        print(render_sms(t, gen.user_key, rng))
    print("\n--- 15 random CSV narration lines (aarav) ---")
    sample2 = rng.sample(debit_txns, min(15, len(debit_txns)))
    for t in sample2:
        sign = "-" if t.direction == "DR" else "+"
        print(
            f"{t.ts.date().isoformat()},{render_csv_narration(t, rng)},{sign}{t.amount_paise/100:.2f},{t.balance_after_paise/100:.2f}"
        )
    print("\n--- month-by-month (aarav): inflow, outflow, closing balance ---")
    for m in gen.month_summary():
        print(
            f"{m['month']}  in={m['inflow_paise']/100:>9,.2f}  out={m['outflow_paise']/100:>9,.2f}  close={m['closing_balance_paise']/100:>9,.2f}"
        )
    print(f"\ndeclined (would-overdraw) debits dropped: {gen.declined_count}")


def write_statement_csv(
    gen: UserGenerator, path: Path, rng: random.Random, n: int = 40
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = gen.txns[-n:] if len(gen.txns) > n else gen.txns
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Narration", "Debit", "Credit", "Balance", "Category"])
        for t in rows:
            debit = f"{t.amount_paise/100:.2f}" if t.direction == "DR" else ""
            credit = f"{t.amount_paise/100:.2f}" if t.direction == "CR" else ""
            writer.writerow(
                [
                    t.ts.strftime("%d/%m/%Y"),
                    render_csv_narration(t, rng),
                    debit,
                    credit,
                    f"{t.balance_after_paise/100:.2f}",
                    t.category,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="FinSight synthetic data generator")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--end-date", type=str, default="2026-11-20")
    parser.add_argument("--as-of-date", type=str, default="2026-11-14")
    args = parser.parse_args()

    end = date.fromisoformat(args.end_date)
    as_of = date.fromisoformat(args.as_of_date)
    start = end - timedelta(days=183)

    persona_gens: dict[str, UserGenerator] = {
        "aarav": build_aarav("aarav", "student", args.seed, start, end, as_of),
        "priya": build_priya("priya", "salaried", args.seed, start, end, as_of),
        "fatima": build_generic_user("fatima", "freelancer", args.seed, start, end),
    }
    for name, gen in persona_gens.items():
        write_user_json(gen, SAMPLE_DIR / f"{name}.json")
        write_user_json(gen, GENERATED_DIR / f"{name}.json")

    for i in range(args.users):
        user_key = f"user{i:04d}"
        archetype_key = pick_archetype(
            random.Random(f"{args.seed}:archetype:{user_key}")
        )
        gen = build_generic_user(user_key, archetype_key, args.seed, start, end)
        write_user_json(gen, GENERATED_DIR / f"{user_key}.json")

    sms_rng = random.Random(f"{args.seed}:sms-samples")
    samples = build_sms_samples(persona_gens, sms_rng)
    sms_path = SAMPLE_DIR / "sms_samples.txt"
    sms_path.write_text(
        "\n".join(json.dumps(s) for s in samples) + "\n", encoding="utf-8"
    )

    csv_rng = random.Random(f"{args.seed}:csv-samples")
    write_statement_csv(
        persona_gens["aarav"], SAMPLE_DIR / "statement_samples.csv", csv_rng
    )

    report_rng = random.Random(f"{args.seed}:report")
    print(
        f"Generated {args.users + 3} users, window {start} .. {end}, AS_OF_DATE={as_of}"
    )
    for name, gen in persona_gens.items():
        end_bal = (
            gen.txns[-1].balance_after_paise
            if gen.txns
            else gen.archetype.starting_balance_paise
        )
        print(
            f"  {name}: {len(gen.txns)} txns, bank={gen.bank}/{gen.secondary_bank}, ending balance Rs.{end_bal/100:,.2f}, declined={gen.declined_count}"
        )
    print_report_preview(persona_gens["aarav"], report_rng)


if __name__ == "__main__":
    main()
