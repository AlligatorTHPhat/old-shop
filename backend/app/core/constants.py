"""Domain enums. They are IntEnums so they compare equal to the raw SMALLINT values in the DB."""

from enum import IntEnum


class RoleId(IntEnum):
    ADMIN = 1
    MODERATOR = 2
    USER = 3


class ProductStatus(IntEnum):
    PENDING = 0
    APPROVED = 1
    REJECTED = 2
    SOLD_OUT = 3


class OrderStatus(IntEnum):
    PENDING = 0
    CONFIRMED = 1
    SHIPPING = 2
    DELIVERED = 3
    CANCELLED = 4


class TransactionStatus(IntEnum):
    PENDING = 0
    SUCCESS = 1
    FLAGGED = 2
    FAILED = 3


class DiscountType(IntEnum):
    FIXED = 0
    PERCENTAGE = 1


class PaymentMethodId(IntEnum):
    """Matches the insert order in database/03_seeds/payment_method/seed.sql."""

    COD = 1
    MOMO = 2
    VNPAY = 3
    PAYPAL = 4
    BANK_TRANSFER = 5


# A review with rating 0 is a violation report, not a real review.
REPORT_RATING = 0
