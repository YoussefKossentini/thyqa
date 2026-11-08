"""Money helpers. Amounts are integer millimes (1 TND = 1000 millimes), never floats."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MILLIMES_PER_TND = 1000


def tnd(amount: int | str | Decimal) -> int:
    """Convert a TND amount ("1500", "12.345", 1500) to integer millimes."""
    if isinstance(amount, float):
        raise TypeError("floats are not allowed for money; pass a str or Decimal")
    value = Decimal(str(amount)) * MILLIMES_PER_TND
    if value != value.to_integral_value():
        raise ValueError(f"{amount} TND has more than 3 decimals")
    return int(value)


def fmt_tnd(millimes: int, style: str = "en") -> str:
    """1500000 -> '1,500 TND' (en), '1500 DT' (derja) or '1 500 DT' (fr). Keeps millimes when present."""
    if not isinstance(millimes, int):
        raise TypeError("millimes must be an int")
    sign = "-" if millimes < 0 else ""
    whole, frac = divmod(abs(millimes), MILLIMES_PER_TND)
    if style == "derja":
        body = f"{whole}" if frac == 0 else f"{whole}.{frac:03d}"
        return f"{sign}{body} DT"
    if style == "fr":
        body = f"{whole:,}".replace(",", "\u202f") if frac == 0 else f"{whole:,}".replace(",", "\u202f") + f",{frac:03d}"
        return f"{sign}{body}\u00a0DT"
    body = f"{whole:,}" if frac == 0 else f"{whole:,}.{frac:03d}"
    return f"{sign}{body} TND"


def split_installments(total: int, n: int) -> list[int]:
    """Split a total into n integer installments; the first one carries the remainder."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if total <= 0:
        raise ValueError("total must be > 0")
    base = total // n
    first = total - base * (n - 1)
    return [first] + [base] * (n - 1)


def apply_discount(price: int, percent: int) -> int:
    """Integer percent discount, rounded half-up to the millime."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    value = (Decimal(price) * (100 - percent) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(value)
