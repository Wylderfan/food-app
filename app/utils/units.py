"""Deliberately small, explicit unit conversions; never guess package sizes/density."""
import math

# dimension, size in the dimension's base unit
_UNITS = {
    'g': ('mass', 1.0), 'kg': ('mass', 1000.0),
    'ml': ('volume', 1.0), 'l': ('volume', 1000.0),
    'count': ('count', 1.0),
}
_ALIASES = {
    'gram': 'g', 'grams': 'g', 'kilogram': 'kg', 'kilograms': 'kg',
    'milliliter': 'ml', 'milliliters': 'ml', 'millilitre': 'ml', 'millilitres': 'ml',
    'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l',
    'piece': 'count', 'pieces': 'count', 'unit': 'count', 'units': 'count',
    'each': 'count', 'counts': 'count',
}


def normalize_unit(unit):
    if not isinstance(unit, str):
        raise ValueError('A supported unit is required.')
    normalized = unit.strip().lower()
    normalized = _ALIASES.get(normalized, normalized)
    if normalized not in _UNITS:
        raise ValueError(f"Unsupported unit '{unit}'; use g, kg, ml, l or count.")
    return normalized


def positive_number(value, label='Quantity'):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite positive number.')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{label} must be a finite positive number.') from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f'{label} must be a finite positive number.')
    return result


def convert_quantity(quantity, from_unit, to_unit):
    """Convert positive quantities between compatible explicit units."""
    quantity = positive_number(quantity)
    source, target = normalize_unit(from_unit), normalize_unit(to_unit)
    dimension, source_factor = _UNITS[source]
    target_dimension, target_factor = _UNITS[target]
    if dimension != target_dimension:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}; incompatible units.")
    result = quantity * (source_factor / target_factor)
    return positive_number(result, 'Converted quantity')


def unit_definitions():
    """JSON-ready conversion definitions for the optional form preview."""
    return {**_UNITS, **{alias: _UNITS[target] for alias, target in _ALIASES.items()}}
