"""Unit conversion skill — length, mass, volume, speed, data, time, temperature."""

import re

# All factors normalise to SI base unit for the category.

_LENGTH: dict[str, float] = {
    "mm": 0.001, "cm": 0.01, "m": 1.0, "meter": 1.0, "meters": 1.0,
    "metre": 1.0, "metres": 1.0, "km": 1000.0, "kilometer": 1000.0,
    "kilometers": 1000.0, "kilometre": 1000.0, "kilometres": 1000.0,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
    "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
}

_MASS: dict[str, float] = {
    "mg": 0.001, "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
    "stone": 6350.29, "stones": 6350.29, "st": 6350.29,
    "ton": 907184.74, "tonne": 1_000_000.0, "t": 1_000_000.0,
}

_VOLUME: dict[str, float] = {
    "ml": 0.001, "l": 1.0, "liter": 1.0, "liters": 1.0,
    "litre": 1.0, "litres": 1.0,
    "gal": 3.78541, "gallon": 3.78541, "gallons": 3.78541,
    "qt": 0.946353, "quart": 0.946353, "quarts": 0.946353,
    "pt": 0.473176, "pint": 0.473176, "pints": 0.473176,
    "cup": 0.236588, "cups": 0.236588,
    "tbsp": 0.0147868, "tablespoon": 0.0147868, "tablespoons": 0.0147868,
    "tsp": 0.00492892, "teaspoon": 0.00492892, "teaspoons": 0.00492892,
    "floz": 0.0295735, "fl_oz": 0.0295735,
}

_SPEED: dict[str, float] = {
    "mps": 1.0, "m/s": 1.0,
    "kph": 0.277778, "km/h": 0.277778, "kmh": 0.277778,
    "mph": 0.44704, "mi/h": 0.44704,
    "knot": 0.514444, "knots": 0.514444, "kn": 0.514444,
    "fps": 0.3048, "ft/s": 0.3048,
}

_DATA: dict[str, float] = {
    "b": 1, "byte": 1, "bytes": 1,
    "kb": 1024, "kib": 1024, "kilobyte": 1024, "kilobytes": 1024,
    "mb": 1024**2, "mib": 1024**2, "megabyte": 1024**2, "megabytes": 1024**2,
    "gb": 1024**3, "gib": 1024**3, "gigabyte": 1024**3, "gigabytes": 1024**3,
    "tb": 1024**4, "tib": 1024**4, "terabyte": 1024**4, "terabytes": 1024**4,
    "pb": 1024**5, "petabyte": 1024**5, "petabytes": 1024**5,
}

_TIME: dict[str, float] = {
    "ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
    "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0,
    "min": 60.0, "mins": 60.0, "minute": 60.0, "minutes": 60.0,
    "hr": 3600.0, "hrs": 3600.0, "h": 3600.0, "hour": 3600.0, "hours": 3600.0,
    "d": 86400.0, "day": 86400.0, "days": 86400.0,
    "wk": 604800.0, "week": 604800.0, "weeks": 604800.0,
    "yr": 31557600.0, "year": 31557600.0, "years": 31557600.0,
}

_TABLES: list[tuple[str, dict]] = [
    ("length",    _LENGTH),
    ("mass",      _MASS),
    ("volume",    _VOLUME),
    ("speed",     _SPEED),
    ("data",      _DATA),
    ("time",      _TIME),
]

_TEMP_UNITS = {"c", "f", "k", "celsius", "fahrenheit", "kelvin"}


def convert(expr: str) -> str:
    """
    Parse and execute a unit conversion.
    Examples:
        "5 miles to km"
        "32 F to C"
        "2 GB to MB"
    """
    expr = expr.strip().lower()
    if not expr:
        return "Please specify a conversion, sir. For example: 5 miles to km."

    # Strip filler
    expr = re.sub(r"\bhow many\b", "", expr)
    expr = re.sub(r"\bis\b", "", expr)

    # Temperature first (non-linear conversion)
    if any(u in expr.split() or f" {u}" in expr for u in ("c", "f", "k")) or \
       any(u in expr for u in ("celsius", "fahrenheit", "kelvin")):
        temp_result = _try_temp(expr)
        if temp_result is not None:
            return temp_result

    # Standard "<num> <unit> to <unit>"
    m = re.match(
        r"^([-+]?\d*\.?\d+)\s*([a-z/_]+)\s*(?:to|in|into)\s*([a-z/_]+)\s*$",
        expr,
    )
    if not m:
        return "I need a format like '5 miles to km', sir."

    value  = float(m.group(1))
    from_u = m.group(2).strip()
    to_u   = m.group(3).strip()

    for _category, table in _TABLES:
        if from_u in table and to_u in table:
            base   = value * table[from_u]
            result = base / table[to_u]
            return f"{_fmt(value)} {from_u} equals {_fmt(result)} {to_u}, sir."

    return f"I don't know how to convert {from_u} to {to_u}, sir."


# ---------------------------------------------------------------------------
# Temperature (special case — offset conversions)
# ---------------------------------------------------------------------------

def _try_temp(expr: str) -> str | None:
    m = re.match(
        r"^([-+]?\d*\.?\d+)\s*(?:degrees?\s*)?([cfk]|celsius|fahrenheit|kelvin)"
        r"\s*(?:to|in|into)\s*(?:degrees?\s*)?([cfk]|celsius|fahrenheit|kelvin)\s*$",
        expr,
    )
    if not m:
        return None

    value  = float(m.group(1))
    from_u = m.group(2)[0]
    to_u   = m.group(3)[0]

    # To Celsius
    if   from_u == "c": celsius = value
    elif from_u == "f": celsius = (value - 32) * 5 / 9
    elif from_u == "k": celsius = value - 273.15
    else:               return None

    # To target
    if   to_u == "c": result = celsius
    elif to_u == "f": result = celsius * 9 / 5 + 32
    elif to_u == "k": result = celsius + 273.15
    else:             return None

    return (
        f"{_fmt(value)} degrees {from_u.upper()} equals "
        f"{_fmt(result)} degrees {to_u.upper()}, sir."
    )


def _fmt(n: float) -> str:
    """Format a number for spoken output."""
    if abs(n) >= 1_000_000:
        return f"{n:,.2f}"
    if n == int(n):
        return f"{int(n):,}"
    if abs(n) < 0.01:
        return f"{n:.6f}".rstrip("0").rstrip(".")
    return f"{n:,.4f}".rstrip("0").rstrip(".")
