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

from finsight_ml.merchant_seed import MERCHANTS_BY_CATEGORY

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

    def to_json(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


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
    subscriptions: list[tuple[str, int]] = field(
        default_factory=list
    )  # (merchant_name, paise)


# Realistic, deliberately modest amount ranges (paise) — these feed a DAILY
# random draw, so ceilings for "big ticket" categories (shopping/education/
# health) are kept small; genuinely large one-off spends come from the
# recurring engine (rent, subscriptions) or scripted overrides, not this pool.
DEFAULT_RANGES: dict[str, tuple[int, int]] = {
    "food_delivery": (8000, 25000),
    "dining_cafe": (10000, 40000),
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

ARCHETYPES = {
    "student": Archetype(
        key="student",
        starting_balance_paise=500000,
        daily_txn_mean=0.9,
        weekend_multiplier=1.3,
        category_weights={
            "food_delivery": 0.32,
            "dining_cafe": 0.14,
            "groceries_qcommerce": 0.08,
            "transport": 0.12,
            "utilities_recharge": 0.04,
            "shopping": 0.14,
            "education": 0.02,
            "health": 0.02,
            "entertainment": 0.08,
            "transfers_friends": 0.04,
        },
        amount_ranges=DEFAULT_RANGES,
        income_kind="allowance",
        income_amount_paise=900000,
        income_day_rule="1st",
        has_rent=False,
        rent_paise=0,
        has_family_transfer=False,
        family_transfer_paise=0,
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
        subscriptions=[
            ("Netflix", 19900),
            ("Spotify", 11900),
            ("Amazon Prime Video", 33000),
            ("Gold's Gym AutoPay", 129900),
        ],
    ),
    "freelancer": Archetype(
        key="freelancer",
        starting_balance_paise=400000,
        daily_txn_mean=0.8,
        weekend_multiplier=1.2,
        category_weights={
            "food_delivery": 0.20,
            "dining_cafe": 0.11,
            "groceries_qcommerce": 0.15,
            "transport": 0.10,
            "utilities_recharge": 0.05,
            "shopping": 0.14,
            "education": 0.04,
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
        subscriptions=[("Adobe Creative Cloud", 167500)],
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
        self.balance_paise = archetype.starting_balance_paise
        self.txns: list[Txn] = []
        self.diwali_week = (date(2026, 11, 3), date(2026, 11, 10))
        self.contacts = self._make_contacts()

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

    # -- helpers -----------------------------------------------------------

    def _pick_merchant(self, category: str) -> tuple[str, str, str, bool]:
        """Returns (merchant_key, surface_name, vpa, is_messy)."""
        rng = self.rng
        if category in ("transfers_family", "transfers_friends"):
            name, vpa = rng.choice(self.contacts[category])
            return name, name, vpa, False
        pool = MERCHANTS_BY_CATEGORY[category]
        if not pool:
            return category, category, rand_qr_vpa(rng), True
        m = rng.choice(pool)
        is_messy = any(marker in m.canonical_name for marker in MESSY_MERCHANT_MARKERS)
        if is_messy:
            vpa = rand_qr_vpa(rng)
        else:
            vpa = rng.choice(m.vpa_patterns)
        return m.canonical_name, m.canonical_name, vpa, is_messy

    def _amount_for(self, category: str) -> int:
        lo, hi = self.archetype.amount_ranges[category]
        return round_rupee(self.rng.randint(lo, hi))

    def _hour_for(self, category: str) -> int:
        rng = self.rng
        buckets = {
            "food_delivery": [12, 13, 20, 21],
            "dining_cafe": [11, 13, 19, 20, 21],
            "groceries_qcommerce": [10, 18, 19],
            "transport": [8, 9, 18, 19],
            "entertainment": [19, 20, 21],
            "shopping": [12, 15, 20, 21],
        }
        if category in buckets:
            return rng.choice(buckets[category])
        return rng.randint(9, 22)

    def _record(
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
    ) -> Txn:
        if direction == "DR":
            self.balance_paise -= amount_paise
        else:
            self.balance_paise += amount_paise
        bank = self.rng.choice(BANKS)
        txn = Txn(
            ts=ts,
            amount_paise=amount_paise,
            direction=direction,
            category=category,
            true_category=category,
            merchant_key=merchant_key,
            surface_name=surface_name,
            vpa=vpa,
            bank=bank,
            balance_after_paise=self.balance_paise,
            is_messy=is_messy,
            note=note,
        )
        self.txns.append(txn)
        return txn

    # -- recurring series ----------------------------------------------------

    def _last_working_day(self, year: int, month: int) -> date:
        if month == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month + 1, 1)
        d = nxt - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    def run_recurring(self) -> None:
        a = self.archetype
        rng = self.rng
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
                self._record(ts, a.income_amount_paise, "CR", "income", name, name, vpa)

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
                    self._record(ts, a.rent_paise, "DR", "rent_housing", key, name, vpa)

            if a.has_family_transfer:
                d = date(m.year, m.month, rng.randint(1, 7))
                if self.start <= d <= self.end:
                    name, vpa = self.contacts["transfers_family"][0]
                    ts = datetime(
                        d.year, d.month, d.day, rng.randint(9, 21), rng.randint(0, 59)
                    )
                    self._record(
                        ts,
                        a.family_transfer_paise,
                        "DR",
                        "transfers_family",
                        name,
                        name,
                        vpa,
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
                    self._record(
                        ts, sub_amount, "DR", "subscriptions", sub_name, sub_name, vpa
                    )

        if a.key == "student":
            self._run_weekly_pattern(
                "Friend Split Payment", "transfers_friends", 15000, 30000
            )
            self._run_periodic_recharge("Jio Recharge", 28)
        if a.key == "freelancer":
            self._run_freelance_credits()

    def _run_weekly_pattern(
        self, merchant_name: str, category: str, lo: int, hi: int
    ) -> None:
        rng = self.rng
        d = self.start + timedelta(days=rng.randint(0, 6))
        while d <= self.end:
            name, vpa = rng.choice(
                self.contacts.get(category, self.contacts["transfers_friends"])
            )
            amount = round_rupee(rng.randint(lo, hi))
            ts = datetime(
                d.year, d.month, d.day, rng.randint(19, 22), rng.randint(0, 59)
            )
            self._record(
                ts, amount, "DR", category, name, name, vpa, note=merchant_name
            )
            d += timedelta(days=7)

    def _run_periodic_recharge(self, merchant_name: str, period_days: int) -> None:
        rng = self.rng
        pool = MERCHANTS_BY_CATEGORY["utilities_recharge"]
        merchant = next((m for m in pool if m.canonical_name == merchant_name), pool[0])
        d = self.start + timedelta(days=rng.randint(0, period_days - 1))
        while d <= self.end:
            vpa = rng.choice(merchant.vpa_patterns)
            amount = round_rupee(rng.randint(19900, 29900))
            ts = datetime(
                d.year, d.month, d.day, rng.randint(8, 20), rng.randint(0, 59)
            )
            self._record(
                ts,
                amount,
                "DR",
                "utilities_recharge",
                merchant.canonical_name,
                merchant.canonical_name,
                vpa,
            )
            d += timedelta(days=period_days)

    def _run_freelance_credits(self) -> None:
        rng = self.rng
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
                    self._record(
                        ts,
                        amount,
                        "CR",
                        "income",
                        "Freelance Client Payment",
                        "Freelance Client Payment",
                        vpa,
                    )
            cur = (
                date(cur.year + 1, 1, 1)
                if cur.month == 12
                else date(cur.year, cur.month + 1, 1)
            )

    # -- daily discretionary spend ------------------------------------------

    def run_discretionary(self) -> None:
        rng = self.rng
        a = self.archetype
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
                amount = self._amount_for(category)
                if self.diwali_week[0] <= d <= self.diwali_week[1] and category in (
                    "shopping",
                    "entertainment",
                ):
                    amount = round_rupee(int(amount * rng.uniform(1.2, 1.6)))
                hour = self._hour_for(category)
                ts = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59))
                self._record(ts, amount, "DR", category, key, name, vpa, is_messy=messy)
            d += timedelta(days=1)

    # -- label injection -----------------------------------------------------

    def inject_anomalies_and_duplicates(
        self, anomaly_rate: float = 0.02, duplicate_rate: float = 0.01
    ) -> None:
        rng = self.rng
        debit_idx = [i for i, t in enumerate(self.txns) if t.direction == "DR"]
        n_anom = max(0, round(len(debit_idx) * anomaly_rate))
        for i in rng.sample(debit_idx, min(n_anom, len(debit_idx))):
            t = self.txns[i]
            t.amount_paise = round_rupee(int(t.amount_paise * rng.uniform(3, 8)))
            t.anomaly = True
        n_dup = max(0, round(len(debit_idx) * duplicate_rate))
        for i in rng.sample(debit_idx, min(n_dup, len(debit_idx))):
            t = self.txns[i]
            dup_ts = t.ts + timedelta(minutes=rng.randint(1, 10))
            self._record(
                dup_ts,
                t.amount_paise,
                t.direction,
                t.category,
                t.merchant_key,
                t.surface_name,
                t.vpa,
            )
            self.txns[-1].duplicate = True

    def apply_label_noise(self, rate: float = 0.03) -> None:
        rng = self.rng
        n = max(0, round(len(self.txns) * rate))
        for i in rng.sample(range(len(self.txns)), min(n, len(self.txns))):
            t = self.txns[i]
            others = [c for c in CATEGORIES if c != t.category]
            t.category = rng.choice(others)

    def sort(self) -> None:
        self.txns.sort(key=lambda t: t.ts)

    def recompute_balances(self) -> None:
        self.sort()
        bal = self.archetype.starting_balance_paise
        for t in self.txns:
            bal += t.amount_paise if t.direction == "CR" else -t.amount_paise
            t.balance_after_paise = bal
        self.balance_paise = bal

    def balance_at_end_of(self, d: date) -> int:
        bal = self.archetype.starting_balance_paise
        for t in sorted(self.txns, key=lambda t: t.ts):
            if t.ts.date() > d:
                break
            bal += t.amount_paise if t.direction == "CR" else -t.amount_paise
        return bal


def distribute_exact(
    total: int, n: int, lo: int, hi: int, rng: random.Random
) -> list[int]:
    """n whole-rupee amounts (in paise, i.e. multiples of 100) within [lo, hi]
    that sum to exactly `total`. `total`/`lo`/`hi` must themselves be
    multiples of 100 for the result to stay whole-rupee."""
    lo_r, hi_r, total_r = lo // 100, hi // 100, total // 100
    vals = [rng.uniform(lo_r, hi_r) for _ in range(n)]
    scale = total_r / sum(vals)
    vals_int = [max(1, round(v * scale)) for v in vals]
    diff = total_r - sum(vals_int)
    vals_int[-1] = max(1, vals_int[-1] + diff)
    return [v * 100 for v in vals_int]


# --------------------------------------------------------------------------
# Scripted persona story beats (overlaid on top of the random simulation)
# --------------------------------------------------------------------------


def apply_aarav_overrides(gen: UserGenerator, as_of: date) -> None:
    rng = gen.rng
    month_start = date(as_of.year, as_of.month, 1)

    # Drop randomly-generated food spend in the "this month so far" window —
    # it gets replaced with the exact scripted set below.
    gen.txns = [
        t
        for t in gen.txns
        if not (
            month_start <= t.ts.date() <= as_of
            and t.category in ("food_delivery", "dining_cafe")
        )
    ]
    # Also clear any anomaly the generic injector happened to place in this
    # window, so there's exactly one unambiguous scripted anomaly.
    gen.txns = [
        t for t in gen.txns if not (month_start <= t.ts.date() <= as_of and t.anomaly)
    ]

    n_food = 41
    food_total_paise = 326000  # ~Rs 3,260
    amounts = distribute_exact(food_total_paise, n_food, 2000, 19900, rng)
    pool = [m for m in MERCHANTS_BY_CATEGORY["food_delivery"]] + [
        m for m in MERCHANTS_BY_CATEGORY["dining_cafe"]
    ]
    days_span = (as_of - month_start).days + 1
    for amount in amounts:
        day_offset = rng.randint(0, days_span - 1)
        d = month_start + timedelta(days=day_offset)
        m = rng.choice(pool)
        is_messy = any(marker in m.canonical_name for marker in MESSY_MERCHANT_MARKERS)
        vpa = rand_qr_vpa(rng) if is_messy else rng.choice(m.vpa_patterns)
        hour = rng.choice([8, 12, 13, 14, 19, 20, 21, 22])
        ts = datetime(d.year, d.month, d.day, hour, rng.randint(0, 59))
        bank = rng.choice(BANKS)
        gen.txns.append(
            Txn(
                ts=ts,
                amount_paise=amount,
                direction="DR",
                category=m.category,
                true_category=m.category,
                merchant_key=m.canonical_name,
                surface_name=m.canonical_name,
                vpa=vpa,
                bank=bank,
                balance_after_paise=0,
                is_messy=is_messy,
            )
        )

    # One unambiguous anomaly: a never-seen merchant, 02:13, Rs 2,499.
    anomaly_day = month_start + timedelta(days=min(6, days_span - 1))
    anomaly_ts = datetime(anomaly_day.year, anomaly_day.month, anomaly_day.day, 2, 13)
    gen.txns.append(
        Txn(
            ts=anomaly_ts,
            amount_paise=249900,
            direction="DR",
            category="shopping",
            true_category="shopping",
            merchant_key="QuickFix Mobile Repair Kiosk",
            surface_name="QuickFix Mobile Repair Kiosk",
            vpa=rand_qr_vpa(rng),
            bank=rng.choice(BANKS),
            balance_after_paise=0,
            anomaly=True,
            note="scripted story-beat anomaly",
        )
    )

    gen.recompute_balances()

    target_balance_paise = 310000  # ~Rs 3,100 on as_of
    current = gen.balance_at_end_of(as_of)
    diff = current - target_balance_paise
    if diff != 0:
        d = month_start + timedelta(days=min(10, days_span - 1))
        ts = datetime(d.year, d.month, d.day, 17, rng.randint(0, 59))
        key, name, vpa, _ = gen._pick_merchant("groceries_qcommerce")
        if diff > 0:
            gen.txns.append(
                Txn(
                    ts=ts,
                    amount_paise=diff,
                    direction="DR",
                    category="groceries_qcommerce",
                    true_category="groceries_qcommerce",
                    merchant_key=key,
                    surface_name=name,
                    vpa=vpa,
                    bank=rng.choice(BANKS),
                    balance_after_paise=0,
                    note="balance calibration",
                )
            )
        else:
            gen.txns.append(
                Txn(
                    ts=ts,
                    amount_paise=-diff,
                    direction="CR",
                    category="income",
                    true_category="income",
                    merchant_key="Cashback Credit",
                    surface_name="Cashback Credit",
                    vpa=next(
                        mm.vpa_patterns[0]
                        for mm in MERCHANTS_BY_CATEGORY["income"]
                        if mm.canonical_name == "Cashback Credit"
                    ),
                    bank=rng.choice(BANKS),
                    balance_after_paise=0,
                    note="balance calibration",
                )
            )
        gen.recompute_balances()


def apply_priya_overrides(gen: UserGenerator, as_of: date) -> None:
    month_start = date(as_of.year, as_of.month, 1)
    month_end = (
        date(as_of.year + 1, 1, 1) - timedelta(days=1)
        if as_of.month == 12
        else date(as_of.year, as_of.month + 1, 1) - timedelta(days=1)
    )
    hiked = False
    for t in gen.txns:
        if (
            t.merchant_key == "Gold's Gym AutoPay"
            and month_start <= t.ts.date() <= month_end
        ):
            t.amount_paise = 159900
            t.price_hike = True
            hiked = True
    if not hiked:
        rng = gen.rng
        d = date(as_of.year, as_of.month, min(10, as_of.day))
        ts = datetime(d.year, d.month, d.day, rng.randint(6, 23), rng.randint(0, 59))
        vpa = next(
            mm.vpa_patterns[0]
            for mm in MERCHANTS_BY_CATEGORY["subscriptions"]
            if mm.canonical_name == "Gold's Gym AutoPay"
        )
        gen.txns.append(
            Txn(
                ts=ts,
                amount_paise=159900,
                direction="DR",
                category="subscriptions",
                true_category="subscriptions",
                merchant_key="Gold's Gym AutoPay",
                surface_name="Gold's Gym AutoPay",
                vpa=vpa,
                bank=rng.choice(BANKS),
                balance_after_paise=0,
                price_hike=True,
            )
        )
    gen.recompute_balances()


def apply_fatima_overrides(gen: UserGenerator, as_of: date) -> None:
    # Stipend + irregular freelance credits already come from the freelancer
    # archetype's recurring engine — nothing to override.
    gen.recompute_balances()


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
        # drop decimals / add a thousands comma if there's a 4+ digit number
        out = re_sub_amount_comma(out, rng)
    if rng.random() < 0.15:
        words = out.split(" ")
        if len(words) > 6:
            cut = rng.randint(3, len(words) - 3)
            out = " ".join(words[:cut]) + "\n" + " ".join(words[cut:])
    if rng.random() < 0.15:
        # strip the balance clause entirely (simulate banks that omit it)
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

PERSONAS = {
    "aarav": ("student", apply_aarav_overrides),
    "priya": ("salaried", apply_priya_overrides),
    "fatima": ("freelancer", apply_fatima_overrides),
}


def pick_archetype(rng: random.Random) -> str:
    keys = [k for k, _ in ARCHETYPE_MIX]
    weights = [w for _, w in ARCHETYPE_MIX]
    return rng.choices(keys, weights=weights, k=1)[0]


def build_user(
    user_key: str,
    archetype_key: str,
    seed: int,
    start: date,
    end: date,
    as_of: date,
    override=None,
) -> UserGenerator:
    rng = random.Random(f"{seed}:{user_key}")
    gen = UserGenerator(user_key, ARCHETYPES[archetype_key], rng, start, end)
    gen.run_recurring()
    gen.run_discretionary()
    gen.inject_anomalies_and_duplicates()
    gen.apply_label_noise()
    gen.recompute_balances()
    if override:
        override(gen, as_of)
    gen.sort()
    return gen


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
        "starting_balance_paise": gen.archetype.starting_balance_paise,
        "ending_balance_paise": gen.balance_paise,
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

    persona_gens: dict[str, UserGenerator] = {}
    for name, (archetype_key, override) in PERSONAS.items():
        gen = build_user(name, archetype_key, args.seed, start, end, as_of, override)
        persona_gens[name] = gen
        write_user_json(gen, SAMPLE_DIR / f"{name}.json")
        write_user_json(gen, GENERATED_DIR / f"{name}.json")

    for i in range(args.users):
        user_key = f"user{i:04d}"
        archetype_key = pick_archetype(
            random.Random(f"{args.seed}:archetype:{user_key}")
        )
        gen = build_user(user_key, archetype_key, args.seed, start, end, as_of)
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
        print(
            f"  {name}: {len(gen.txns)} txns, ending balance Rs.{gen.balance_paise/100:,.2f}"
        )
    print_report_preview(persona_gens["aarav"], report_rng)


if __name__ == "__main__":
    main()
