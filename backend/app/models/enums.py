from enum import StrEnum


class Direction(StrEnum):
    DR = "DR"
    CR = "CR"


class TxnSource(StrEnum):
    SMS = "sms"
    CSV = "csv"
    PDF = "pdf"
    SEED = "seed"


class Category(StrEnum):
    FOOD_DELIVERY = "food_delivery"
    DINING_CAFE = "dining_cafe"
    GROCERIES_QCOMMERCE = "groceries_qcommerce"
    TRANSPORT = "transport"
    RENT_HOUSING = "rent_housing"
    UTILITIES_RECHARGE = "utilities_recharge"
    SUBSCRIPTIONS = "subscriptions"
    SHOPPING = "shopping"
    EDUCATION = "education"
    HEALTH = "health"
    ENTERTAINMENT = "entertainment"
    TRANSFERS_FAMILY = "transfers_family"
    TRANSFERS_FRIENDS = "transfers_friends"
    INCOME = "income"


class AlertType(StrEnum):
    ANOMALY = "anomaly"
    DUPLICATE = "duplicate"
    PRICE_HIKE = "price_hike"
    SCAM = "scam"


class AlertStatus(StrEnum):
    OPEN = "open"
    OK = "ok"
    NOT_ME = "not_me"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
