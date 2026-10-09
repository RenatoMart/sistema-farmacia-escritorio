import json
import hashlib
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from adell.domain import (DATE_FMT, convert_units_to_base, ensure_pricing, legacy_price_basis, migrate_legacy_product,
                          money, parse_date, resolve_price, sellable_levels, today_str, unit_factor, units_per_package)


DEFAULT_SETTINGS = {
    "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
    "upcoming_days": 60,
}


# Única cuenta de una instalación nueva. Cambia su contraseña desde «Personal» al primer ingreso;
# el resto del personal se crea desde la propia aplicación.
DEFAULT_USERS = {
    "admin": {
        "name": "Administrador",
        "username": "admin",
        "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
        "role": "admin",
        "permissions": ["all", "manage_staff", "change_staff_passwords"]
    },
}


def _user_config_dir() -> Path:
    """Carpeta de configuración del usuario (no la del código, que no es escribible al empaquetar el .exe)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "farmacia"


class PathConfig:
    """Recuerda en qué carpeta se guardan los datos de la farmacia.

    La preferencia vive en la carpeta de configuración del usuario. Por compatibilidad, si no existe
    allí se lee el `path_config.json` que versiones anteriores guardaban junto al programa.
    """

    def __init__(self):
        self.config_file = _user_config_dir() / "path_config.json"
        self.legacy_file = Path(__file__).resolve().parents[1] / "path_config.json"

    def _read(self, file: Path) -> Optional[Path]:
        try:
            path = Path(json.loads(file.read_text(encoding="utf-8")).get("data_path") or "")
        except (OSError, ValueError):
            return None
        return path if path.is_dir() else None

    def get_data_path(self) -> Optional[Path]:
        """Carpeta de datos configurada, o None si falta o ya no existe."""
        return self._read(self.config_file) or self._read(self.legacy_file)

    def has_config(self) -> bool:
        return self.get_data_path() is not None

    def set_data_path(self, path: Path) -> bool:
        """Guarda la carpeta de datos elegida."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(json.dumps({"data_path": str(path.resolve())}, indent=2), encoding="utf-8")
            return True
        except OSError as e:
            print(f"Error guardando configuración: {e}")
            return False


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        """Inicializa el DataStore con la ruta de datos especificada."""
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.products_file = self.data_dir / "products.json"
        self.movements_file = self.data_dir / "movements.json"
        self.settings_file = self.data_dir / "settings.json"
        self.activities_file = self.data_dir / "activities.json"
        self.users_file = self.data_dir / "users.json"
        self.products = self._load(self.products_file, self._seed_products())
        self.movements = self._load(self.movements_file, [])
        self.settings = self._load(self.settings_file, DEFAULT_SETTINGS)
        self.activities = self._load(self.activities_file, [])
        self.users = self._load(self.users_file, DEFAULT_USERS)  # Cargar usuarios
        self._migrate_pricing()

    def _load(self, path: Path, default):
        if not path.exists():
            path.write_text(json.dumps(default, indent=2), encoding="utf-8")
            return default
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _save(self, path: Path, payload) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _migrate_pricing(self) -> None:
        """Convierte datos con un solo precio sin unidad (acquisition_price/sale_price) al modelo por niveles.

        Se ejecuta una vez (marca `pricing_version`), guarda copias `*_pre_pricing_backup.json` y deja
        cada producto migrado con `needs_price_review` para que el dueño confirme sus precios.
        """
        pending = [p for p in self.products if p.get("pricing_version") != 2]
        if not pending:
            return
        for source in (self.products_file, self.movements_file):
            backup = source.with_name(source.stem + "_pre_pricing_backup.json")
            if source.exists() and not backup.exists():
                backup.write_bytes(source.read_bytes())

        legacy = {p["id"]: (p, legacy_price_basis(p), float(p.get("sale_price", 0) or 0),
                            float(p.get("acquisition_price", 0) or 0)) for p in pending}
        for m in self.movements:
            if "price_basis" in m:
                continue
            if m.get("product_id") not in legacy:
                # Producto ya eliminado: no se conoce su jerarquía; se conserva el cálculo antiguo (cantidad × precio)
                sale = float(m.pop("sale_price", 0) or 0)
                cost = float(m.pop("acquisition_price", 0) or 0)
                qty = int(m["quantity"])
                m.update(base_quantity=qty, price_basis="legacy_unknown",
                         unit_price=money(sale if m["type"] == "Salida" else cost),
                         line_total=money(qty * (sale if m["type"] == "Salida" else cost)))
                if m["type"] == "Salida":
                    m.update(unit_cost_base=round(cost, 6), line_cost=money(qty * cost))
                continue
            product, basis, _, _ = legacy[m["product_id"]]
            hierarchy = product.get("unit_hierarchy", {})
            upp = units_per_package(hierarchy)
            sale = float(m.pop("sale_price", 0) or 0)
            cost = float(m.pop("acquisition_price", 0) or 0)
            per_base_sale = sale / upp if basis == "legacy_package" else sale
            per_base_cost = cost / upp if basis == "legacy_package" else cost
            base_q = convert_units_to_base(int(m["quantity"]), m.get("unit_type", "base_unit"), hierarchy)
            factor = unit_factor(hierarchy, m.get("unit_type", "base_unit"))
            m["base_quantity"] = base_q
            m["price_basis"] = basis
            if m["type"] == "Salida":
                m.update(unit_price=money(per_base_sale * factor), line_total=money(base_q * per_base_sale),
                         unit_cost_base=round(per_base_cost, 6), line_cost=money(base_q * per_base_cost))
            else:
                m.update(unit_price=money(per_base_cost * factor), line_total=money(base_q * per_base_cost))
        for product, _, _, _ in legacy.values():
            migrate_legacy_product(product)
        self.save_products()
        self.save_movements()

    def _seed_products(self) -> List[Dict]:
        return [
            {
                "id": str(uuid4()),
                "commercial_name": "Paracetamol 500",
                "generic_name": "Acetaminofen",
                "laboratory": "Laboratorio Vida",
                "therapeutic_action": "Analgésico",
                "description": "Tabletas para dolor leve",
                "presentation": "Blister",
                "package_units": 10,
                "concentration_mg": 500,
                "stock": 120,
                "expiry_date": (date.today() + timedelta(days=180)).strftime(DATE_FMT),
                "acquisition_price": 0.12,
                "sale_price": 0.35,
                "last_updated": today_str(),
            },
            {
                "id": str(uuid4()),
                "commercial_name": "Amoxicilina 500",
                "generic_name": "Amoxicilina",
                "laboratory": "SaludPlus",
                "therapeutic_action": "Antibiótico",
                "description": "Cápsulas antibióticas",
                "presentation": "Caja",
                "package_units": 20,
                "concentration_mg": 500,
                "stock": 60,
                "expiry_date": (date.today() + timedelta(days=45)).strftime(DATE_FMT),
                "acquisition_price": 0.55,
                "sale_price": 0.95,
                "last_updated": today_str(),
            },
        ]

    def save_products(self) -> None:
        self._save(self.products_file, self.products)

    def save_movements(self) -> None:
        self._save(self.movements_file, self.movements)

    def save_settings(self) -> None:
        self._save(self.settings_file, self.settings)

    def search_products(self, query: str = "", presentation: str = "Todos", sort_by_expiry: bool = True) -> List[Dict]:
        query = query.lower().strip()
        matches: List[Dict] = []
        for product in self.products:
            if query and query not in " ".join(str(v).lower() for v in product.values()):
                continue
            if presentation != "Todos" and product["presentation"] != presentation:
                continue
            matches.append(product)
        if sort_by_expiry:
            matches.sort(key=lambda p: parse_date(p.get("expiry_date", "9999-12-31")))
        return matches

    def get_product(self, product_id: str) -> Optional[Dict]:
        return next((p for p in self.products if p["id"] == product_id), None)

    def upsert_product(self, payload: Dict) -> None:
        payload["last_updated"] = today_str()
        existing = self.get_product(payload["id"])
        if existing:
            existing.update(payload)
            product = existing
        else:
            self.products.append(payload)
            product = payload
        ensure_pricing(product)
        self.save_products()

    def delete_product(self, product_id: str) -> None:
        self.products = [p for p in self.products if p["id"] != product_id]
        self.save_products()

    def adjust_stock(self, product_id: str, delta: int, unit_type: str = "base_unit") -> None:
        """
        Ajusta el stock de un producto considerando el tipo de unidad.
        delta: cantidad a ajustar (positivo para entrada, negativo para salida)
        unit_type: tipo de unidad ("base_unit", "intermediate_unit", "package_unit")
        """
        product = self.get_product(product_id)
        if not product:
            raise ValueError("Producto no encontrado")

        # Convertir delta a unidades base
        unit_hierarchy = product.get("unit_hierarchy", {})
        base_delta = convert_units_to_base(abs(delta), unit_type, unit_hierarchy)
        if delta < 0:
            base_delta = -base_delta

        new_stock = product["stock"] + base_delta
        if new_stock < 0:
            raise ValueError("Stock insuficiente")

        product["stock"] = new_stock
        product["last_updated"] = today_str()
        self.save_products()

    def record_movement(self, movement: Dict) -> None:
        """Registra una entrada/salida y actualiza stock y costo promedio.

        El movimiento queda como foto inmutable: guarda cantidad base, precio por unidad, total y
        costo, de modo que editar precios después no altere los reportes pasados.
        - Salida: `unit_price` es el precio de venta de UNA unidad del nivel `unit_type` (si no se
          indica, se toma del producto); `line_cost` usa el costo promedio vigente.
        - Entrada: `unit_price` es lo que costó UNA unidad de ese nivel (p. ej. una caja); el costo
          promedio por unidad base se recalcula ponderando con el stock existente.
        """
        for field in ("product_id", "type", "quantity", "unit_type"):
            if field not in movement:
                raise ValueError(f"Campo requerido faltante: {field}")
        product = self.get_product(movement["product_id"])
        if not product:
            raise ValueError("Producto no encontrado")
        ensure_pricing(product)
        hierarchy = product.get("unit_hierarchy", {})
        level, qty = movement["unit_type"], int(movement["quantity"])
        base_qty = convert_units_to_base(qty, level, hierarchy)
        factor = unit_factor(hierarchy, level)
        avg = float(product["avg_cost_base"])

        if movement["type"] == "Salida":
            if level not in sellable_levels(product):
                raise ValueError("Este producto no se vende en esa unidad")
            unit_price = movement.get("unit_price")
            unit_price = resolve_price(product, level) if unit_price is None else float(unit_price)
            movement.update(unit_price=money(unit_price), line_total=money(qty * unit_price),
                            unit_cost_base=round(avg, 6), line_cost=money(base_qty * avg))
        else:
            unit_price = movement.get("unit_price")
            unit_price = avg * factor if unit_price is None else float(unit_price)
            cost_base = unit_price / factor
            on_hand = max(int(product["stock"]), 0)
            new_avg = (on_hand * avg + base_qty * cost_base) / (on_hand + base_qty)
            movement.update(unit_price=money(unit_price), line_total=money(qty * unit_price))
            product["avg_cost_base"] = round(new_avg, 6)
            product["cost_per_package"] = money(cost_base * units_per_package(hierarchy))
        movement.update(base_quantity=base_qty, price_basis="v2")

        self.adjust_stock(movement["product_id"], base_qty if movement["type"] != "Salida" else -base_qty, "base_unit")
        self.movements.append(movement)
        self.save_movements()

    def get_movements(self, movement_type: str = "Todos", start: Optional[date] = None, end: Optional[date] = None, username: Optional[str] = None) -> List[Dict]:
        def within_range(m: Dict) -> bool:
            move_date = parse_date(m["date"])
            if start and move_date < start:
                return False
            if end and move_date > end:
                return False
            if movement_type != "Todos" and m["type"] != movement_type:
                return False
            if username and m.get("username") != username:
                return False
            return True
        return [m for m in self.movements if within_range(m)]

    def upcoming_products(self, days: Optional[int] = None) -> List[Dict]:
        days = days or self.settings.get("upcoming_days", 60)
        limit = date.today() + timedelta(days=days)
        upcoming = [
            p for p in self.products
            if p["stock"] > 0 and parse_date(p["expiry_date"]) <= limit
        ]
        upcoming.sort(key=lambda p: parse_date(p["expiry_date"]))
        return upcoming

    def log_activity(self, username: str, user_name: str, action: str, details: Dict) -> None:
        """Registra una actividad del usuario"""
        activity = {
            "id": str(uuid4()),
            "username": username,
            "user_name": user_name,
            "action": action,
            "details": details,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.activities.append(activity)
        self._save(self.activities_file, self.activities)

    def get_activities(self, username: Optional[str] = None, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict]:
        """Obtiene actividades filtradas por usuario y/o fecha"""
        filtered = self.activities

        if username:
            filtered = [a for a in filtered if a.get("username") == username]

        if start_date or end_date:
            def within_range(activity: Dict) -> bool:
                activity_date = datetime.strptime(activity["timestamp"], "%Y-%m-%d %H:%M:%S").date()
                if start_date and activity_date < start_date:
                    return False
                if end_date and activity_date > end_date:
                    return False
                return True
            filtered = [a for a in filtered if within_range(a)]

        return sorted(filtered, key=lambda x: x["timestamp"], reverse=True)

    def save_users(self) -> None:
        """Guarda los usuarios en el archivo"""
        self._save(self.users_file, self.users)

    def get_user(self, username: str) -> Optional[Dict]:
        """Obtiene un usuario por su username"""
        return self.users.get(username)

    def get_all_users(self) -> Dict:
        """Obtiene todos los usuarios"""
        return self.users

    def add_user(self, username: str, name: str, password: str, role: str = "personal") -> None:
        """Agrega un nuevo usuario"""
        permissions = ["register_entry", "register_sale", "view_reports", "change_own_password"]
        if role == "admin":
            permissions = ["all", "manage_staff", "change_staff_passwords"]
        elif role == "superadmin":
            permissions = ["all", "manage_all_users", "change_all_passwords"]

        self.users[username] = {
            "name": name,
            "username": username,
            "password_hash": hashlib.sha256(password.encode()).hexdigest(),
            "role": role,
            "permissions": permissions
        }
        self.save_users()

    def update_user_password(self, username: str, new_password: str) -> None:
        """Actualiza la contraseña de un usuario"""
        if username in self.users:
            self.users[username]["password_hash"] = hashlib.sha256(new_password.encode()).hexdigest()
            self.save_users()

    def delete_user(self, username: str) -> None:
        """Elimina un usuario"""
        if username in self.users and username not in ["superadmin", "admin"]:  # No permitir eliminar admins
            del self.users[username]
            self.save_users()

    def verify_password(self, username: str, password: str) -> bool:
        """Verifica la contraseña de un usuario"""
        user = self.get_user(username)
        if user:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            return user["password_hash"] == password_hash
        return False

    def can_change_password(self, current_user_role: str, target_username: str) -> bool:
        """Verifica si el usuario actual puede cambiar la contraseña del usuario objetivo"""
        if current_user_role == "superadmin":
            return True  # ADMIN puede cambiar todas las contraseñas
        elif current_user_role == "admin":
            target_user = self.get_user(target_username)
            # Admin puede cambiar su propia contraseña y la de personal
            return target_user and target_user["role"] in ["admin", "personal"]
        else:
            return False  # Personal solo puede cambiar su propia contraseña (manejado en UI)

    def get_users_by_role(self, role: str) -> List[Dict]:
        """Obtiene usuarios filtrados por rol"""
        return [user for user in self.users.values() if user["role"] == role]
