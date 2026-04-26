"""
Thin wrapper around USDA FoodData Central /foods/search.

The search endpoint returns nutrient values normalised to per 100 g (or 100 ml
for liquids), regardless of dataType — Branded foods include `servingSize` /
`servingSizeUnit` for the label serving but the `foodNutrients` array still
reports per 100 g. We surface results as per-100-unit so the user can review
and adjust serving size after import.
"""
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json

SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
TIMEOUT_SECONDS = 8

# FDC nutrient IDs we care about
NUTRIENT_IDS = {
    "calories": 1008,   # Energy (kcal)
    "protein":  1003,
    "carbs":    1005,   # Carbohydrate, by difference
    "fat":      1004,   # Total lipid (fat)
    "fiber":    1079,   # Fiber, total dietary
    "sugar":    2000,   # Sugars, total including NLEA
}


class USDAError(Exception):
    pass


def search_foods(query, api_key, page_size=10):
    if not query or not query.strip():
        return []

    params = {
        "query": query.strip(),
        "api_key": api_key,
        "pageSize": page_size,
        "dataType": "Branded,Foundation,SR Legacy",
    }
    url = f"{SEARCH_URL}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 403:
            raise USDAError("USDA API key rejected. Check USDA_API_KEY in .env.")
        if e.code == 429:
            raise USDAError("USDA rate limit hit. DEMO_KEY allows 30 requests/hour — sign up for a free key.")
        raise USDAError(f"USDA API returned {e.code}.") from e
    except URLError as e:
        raise USDAError(f"Could not reach USDA API: {e.reason}") from e

    return [_simplify(food) for food in payload.get("foods", [])]


def _simplify(food):
    """Normalise an FDC food record into the app's ingredient shape (per 100 g/ml)."""
    nutrients = {n.get("nutrientId"): n.get("value") for n in food.get("foodNutrients", [])}
    serving_unit = (food.get("servingSizeUnit") or "g").lower()
    if serving_unit not in ("g", "ml"):
        serving_unit = "g"

    return {
        "fdcId": food.get("fdcId"),
        "name": (food.get("description") or "").strip(),
        "brand": (food.get("brandOwner") or food.get("brandName") or "").strip() or None,
        "dataType": food.get("dataType"),
        "servingSize": 100,
        "servingUnit": serving_unit,
        "calories": _val(nutrients, "calories"),
        "protein":  _val(nutrients, "protein"),
        "carbs":    _val(nutrients, "carbs"),
        "fat":      _val(nutrients, "fat"),
        "fiber":    _val(nutrients, "fiber"),
        "sugar":    _val(nutrients, "sugar"),
    }


def _val(nutrients, key):
    v = nutrients.get(NUTRIENT_IDS[key])
    return float(v) if isinstance(v, (int, float)) else 0
