from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple




DATE_FMT = "%Y-%m-%d"


PRESENTATIONS = [
    "Caja",
    "Blister",
    "Frasco",
    "Botella",
    "Tableta",
    "Unidad",
    "Inhalador"
]


UNIT_TYPES = [
    "base_unit",           # Unidad más pequeña (tableta, cápsula, ml)
    "intermediate_unit",   # Unidad intermedia (blister)
    "package_unit"         # Unidad de empaque (caja, frasco)
]


def today_str() -> str:
    return date.today().strftime(DATE_FMT)


def parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FMT).date()


def calculate_total_base_units(unit_hierarchy: Dict) -> int:
    """Calcula el total de unidades base a partir de la jerarquía."""
    if not unit_hierarchy:
        return 0

    units_per_intermediate = unit_hierarchy.get("units_per_intermediate", 1)
    intermediate_per_package = unit_hierarchy.get("intermediate_per_package", 1)

    return units_per_intermediate * intermediate_per_package


def get_unit_display_info(product: Dict) -> Tuple[str, str, str]:
    """
    Retorna información de visualización de unidades.
    Returns: (base_unit_name, intermediate_unit_name, package_unit_name)
    """
    unit_hierarchy = product.get("unit_hierarchy", {})

    base_unit = unit_hierarchy.get("base_unit", "Unidad")
    intermediate_unit = unit_hierarchy.get("intermediate_unit")
    if str(intermediate_unit).strip().lower() in ("", "none"):  # datos antiguos guardaban el texto "None"
        intermediate_unit = None
    package_unit = unit_hierarchy.get("package_unit", product.get("presentation", "Unidad"))

    return base_unit, intermediate_unit, package_unit


def convert_units_to_base(quantity: int, unit_type: str, unit_hierarchy: Dict) -> int:
    """
    Convierte una cantidad de cualquier tipo de unidad a unidades base.
    """
    if unit_type == "base_unit":
        return quantity
    elif unit_type == "intermediate_unit":
        return quantity * unit_hierarchy.get("units_per_intermediate", 1)
    elif unit_type == "package_unit":
        units_per_intermediate = unit_hierarchy.get("units_per_intermediate", 1)
        intermediate_per_package = unit_hierarchy.get("intermediate_per_package", 1)
        return quantity * units_per_intermediate * intermediate_per_package
    else:
        return quantity


def convert_base_to_units(base_quantity: int, unit_hierarchy: Dict) -> Tuple[int, int, int]:
    """
    Convierte unidades base a la representación completa.
    Returns: (packages, intermediates_remaining, base_units_remaining)
    """
    if not unit_hierarchy:
        return 0, 0, base_quantity

    units_per_intermediate = unit_hierarchy.get("units_per_intermediate", 1)
    intermediate_per_package = unit_hierarchy.get("intermediate_per_package", 1)

    # Calcular paquetes completos
    units_per_package = units_per_intermediate * intermediate_per_package
    packages = base_quantity // units_per_package
    remaining_after_packages = base_quantity % units_per_package

    # Calcular intermedios restantes
    intermediates = remaining_after_packages // units_per_intermediate
    base_units = remaining_after_packages % units_per_intermediate

    return packages, intermediates, base_units


# ---------------------------------------------------------------------------
# Niveles de unidad, precios y costos
#
# Un producto se compra y se vende en hasta tres niveles: unidad base (tableta, ml),
# empaque intermedio (blister) y empaque completo (caja, frasco). El stock vive siempre
# en unidades base. Cada nivel puede tener su propio precio de venta (`prices`), porque
# en el mostrador la tableta suelta suele costar más que el prorrateo de la caja.
# El costo se guarda como promedio ponderado por unidad base (`avg_cost_base`).
# ---------------------------------------------------------------------------
LEVELS = ("base_unit", "intermediate_unit", "package_unit")  # de menor a mayor
UNCOUNTABLE_BASES = {"ml", "g", "dosis"}  # no se venden sueltos: solo el empaque completo
DEFAULT_MARKUP = 0.10  # recargo sugerido al vender por fracciones de una caja


def money(value) -> float:
    """Redondea a céntimos (mitad hacia arriba), sin errores de coma flotante."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def ceil_to(value, step: float = 0.10) -> float:
    """Redondea hacia arriba al múltiplo de `step` (cómo se cobra en mostrador)."""
    steps = (Decimal(str(value)) / Decimal(str(step))).to_integral_value(rounding=ROUND_CEILING)
    return float((steps * Decimal(str(step))).quantize(Decimal("0.01")))


def units_per_package(hierarchy: Dict) -> int:
    return max(1, int(hierarchy.get("units_per_intermediate", 1) or 1) * int(hierarchy.get("intermediate_per_package", 1) or 1))


def unit_factor(hierarchy: Dict, level: str) -> int:
    """Cuántas unidades base hay en una unidad del nivel dado."""
    return {"base_unit": 1, "intermediate_unit": max(1, int(hierarchy.get("units_per_intermediate", 1) or 1))}.get(
        level, units_per_package(hierarchy))


def unit_levels(product: Dict) -> List[str]:
    """Niveles que existen para el producto, de menor a mayor. La unidad base siempre existe."""
    hierarchy = product.get("unit_hierarchy", {})
    levels = ["base_unit"]
    if get_unit_display_info(product)[1]:
        levels.append("intermediate_unit")
    if units_per_package(hierarchy) > 1:
        levels.append("package_unit")
    return levels


def level_label(product: Dict, level: str) -> str:
    base_unit, intermediate_unit, package_unit = get_unit_display_info(product)
    return {"base_unit": base_unit, "intermediate_unit": intermediate_unit or base_unit}.get(level, package_unit)


def default_sellable(product: Dict) -> List[str]:
    """Niveles en que se vende por defecto: los líquidos, inhaladores y geles solo por empaque completo."""
    levels = unit_levels(product)
    base = (product.get("unit_hierarchy", {}).get("base_unit") or "").lower()
    if base in UNCOUNTABLE_BASES and "package_unit" in levels:
        return ["package_unit"]
    return levels


def sellable_levels(product: Dict) -> List[str]:
    """Niveles en que se puede vender, en orden de menor a mayor (nunca vacío)."""
    levels = unit_levels(product)
    chosen = product.get("sellable_units") or default_sellable(product)
    result = [lvl for lvl in levels if lvl in chosen]
    return result or [levels[-1]]


def suggested_price(package_price: float, hierarchy: Dict, level: str, markup: float = DEFAULT_MARKUP) -> float:
    """Precio sugerido para un nivel a partir del precio del empaque completo."""
    if level == "package_unit":
        return money(package_price)
    raw = package_price / units_per_package(hierarchy) * unit_factor(hierarchy, level) * (1 + markup)
    return ceil_to(raw, 0.05 if raw < 1 else 0.10)


def resolve_price(product: Dict, level: str) -> float:
    """Precio de venta de UNA unidad del nivel dado: el fijado por el dueño o, si falta, el sugerido."""
    prices = product.get("prices") or {}
    if prices.get(level) is not None:
        return float(prices[level])
    hierarchy = product.get("unit_hierarchy", {})
    package_price = prices.get("package_unit")
    if package_price is None and prices.get("base_unit") is not None:
        package_price = prices["base_unit"] * units_per_package(hierarchy)
    return suggested_price(package_price, hierarchy, level) if package_price is not None else 0.0


def package_price(product: Dict) -> float:
    """Precio del empaque completo (o de la unidad base si el producto no tiene empaque)."""
    top = unit_levels(product)[-1]
    return resolve_price(product, top)


def price_summary(product: Dict) -> str:
    """Texto corto para tablas: precio del nivel de venta más alto, p. ej. "S/ 5.25 / Frasco"."""
    level = sellable_levels(product)[-1]
    return f"S/ {resolve_price(product, level):.2f} / {level_label(product, level)}"


def avg_cost_per_level(product: Dict, level: str) -> float:
    return float(product.get("avg_cost_base", 0.0)) * unit_factor(product.get("unit_hierarchy", {}), level)


def ensure_pricing(product: Dict) -> Dict:
    """Completa los campos de precio de un producto (idempotente). Devuelve el mismo dict."""
    product.setdefault("prices", {})
    product.setdefault("avg_cost_base", 0.0)
    product.setdefault("cost_per_package", 0.0)
    if not product.get("sellable_units"):
        product["sellable_units"] = default_sellable(product)
    product["pricing_version"] = 2
    return product


def legacy_price_basis(product: Dict) -> str:
    """Los datos antiguos tenían un solo precio sin unidad. Líquidos, inhaladores y geles (base no
    contable) lo guardaban por empaque; el resto, por unidad base."""
    base = (product.get("unit_hierarchy", {}).get("base_unit") or "").lower()
    return "legacy_package" if base in UNCOUNTABLE_BASES else "legacy_base"


def migrate_legacy_product(product: Dict) -> str:
    """Convierte acquisition_price/sale_price antiguos al modelo por niveles. Devuelve la base usada."""
    hierarchy = product.get("unit_hierarchy", {})
    upp = units_per_package(hierarchy)
    basis = legacy_price_basis(product)
    sale, cost = float(product.get("sale_price", 0) or 0), float(product.get("acquisition_price", 0) or 0)
    per_base_sale = sale / upp if basis == "legacy_package" else sale
    per_base_cost = cost / upp if basis == "legacy_package" else cost
    if "intermediate_unit" in hierarchy and not get_unit_display_info(product)[1]:
        hierarchy["intermediate_unit"] = None
    product["sellable_units"] = default_sellable(product)
    product["prices"] = {lvl: money(per_base_sale * unit_factor(hierarchy, lvl)) for lvl in sellable_levels(product)}
    product["avg_cost_base"] = round(per_base_cost, 6)
    product["cost_per_package"] = money(per_base_cost * upp)
    product["needs_price_review"] = True
    product["pricing_version"] = 2
    for key in ("sale_price", "acquisition_price"):
        product.pop(key, None)
    return basis


# ---------------------------------------------------------------------------
# Presentación de cantidades y existencias
# ---------------------------------------------------------------------------
def movement_amounts(movement: Dict) -> Tuple[float, float, float]:
    """(total, costo, utilidad) de un movimiento, tal como se guardó al registrarlo.

    En una entrada el total es lo invertido y no hay utilidad; en una salida la utilidad es total − costo.
    """
    total = float(movement.get("line_total", 0.0))
    if movement.get("type") != "Salida":
        return total, 0.0, 0.0
    cost = float(movement.get("line_cost", 0.0))
    return total, cost, money(total - cost)


def plural(count: int, name: str) -> str:
    """Plural en español de un nombre de unidad ("Caja"→"Cajas", "Unidad"→"Unidades")."""
    lower = name.lower()
    if count == 1 or lower in {"ml", "g", "kg", "mg", "blister"} or lower.endswith(("s", "x")):
        return name if lower != "blister" or count == 1 else name + "s"
    return name + ("s" if lower[-1] in "aeiou" else "es")


def format_quantity(product: Dict, unit_type: str, quantity: int) -> str:
    """Texto legible de una cantidad en la unidad indicada, p. ej. "3 Cajas" o "1 Blister"."""
    return f"{quantity} {plural(quantity, level_label(product, unit_type))}"


def stock_breakdown(product: Dict) -> List[Tuple[int, str]]:
    """Existencias desglosadas por nivel, de mayor a menor: [(2, 'Cajas'), (1, 'Blister'), (5, 'Tabletas')]."""
    remaining = int(product.get("stock", 0))
    hierarchy = product.get("unit_hierarchy", {})
    parts: List[Tuple[int, str]] = []
    for level in reversed(unit_levels(product)):
        factor = unit_factor(hierarchy, level)
        count, remaining = (remaining // factor, remaining % factor) if level != "base_unit" else (remaining, 0)
        if count:
            parts.append((count, plural(count, level_label(product, level))))
    return parts


def format_stock_display(product: Dict) -> str:
    """Existencias en lenguaje de mostrador: "2 Cajas + 1 Blister + 5 Tabletas (65)"."""
    stock = int(product.get("stock", 0))
    parts = stock_breakdown(product)
    if not parts:
        base = product.get("unit_hierarchy", {}).get("base_unit", "unidades")
        return f"0 {plural(0, base)}"
    text = " + ".join(f"{n} {name}" for n, name in parts)
    return f"{text} ({stock})" if len(parts) > 1 else text


def unit_choices(product: Dict, for_sale: bool = False) -> Dict[str, str]:
    """Unidades en que se puede mover un producto: {texto a mostrar: nivel}.

    En una venta solo se ofrecen los niveles vendibles; en una entrada, todos los que existen.
    """
    levels = sellable_levels(product) if for_sale else unit_levels(product)
    choices: Dict[str, str] = {}
    for level in levels:
        label = level_label(product, level)
        if label not in choices:
            choices[label] = level
    return choices
