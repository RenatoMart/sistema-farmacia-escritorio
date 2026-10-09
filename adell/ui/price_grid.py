"""Cuadrícula de precios de venta por nivel de unidad (caja / blister / unidad suelta).

Se usa en el formulario de producto y en el alta de producto nuevo en Entradas. El dueño marca en qué
unidades vende el producto y fija el precio de cada una; mientras no escriba un precio propio para un
nivel, se muestra el sugerido (prorrateo del empaque + recargo, redondeado a mostrador).
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from adell.domain import (default_sellable, level_label, money, suggested_price, unit_factor, unit_levels)
from adell.ui.theme import THEME, ui_font


def hierarchy_from_vars(vars_: Dict[str, tk.StringVar]) -> Dict:
    """Producto mínimo (presentación + jerarquía) a partir de los campos de un formulario.

    Lanza ValueError si un número está a medias; quien llama decide si ignorarlo mientras se escribe.
    """
    presentation = vars_["presentation"].get() or "Unidad"
    return {"presentation": presentation, "unit_hierarchy": {
        "base_unit": vars_["base_unit"].get().strip() or "Unidad",
        "intermediate_unit": vars_["intermediate_unit"].get().strip() or None,
        "package_unit": presentation,
        "units_per_intermediate": int(float(vars_["units_per_intermediate"].get() or 1)),
        "intermediate_per_package": int(float(vars_["intermediate_per_package"].get() or 1)),
    }}


class PriceGrid(ttk.Frame):
    def __init__(self, parent, provider: Callable[[], Dict], surface: bool = True) -> None:
        """`provider()` devuelve el producto (presentación + unit_hierarchy) con sus unidades actuales."""
        self._style = "CardInner.TFrame" if surface else "Main.TFrame"
        self._label_style = "Card.TLabel" if surface else "TLabel"
        self._muted_style = "CardMuted.TLabel" if surface else "Muted.TLabel"
        self._check_style = "Card.TCheckbutton" if surface else "TCheckbutton"
        super().__init__(parent, style=self._style)
        self.provider = provider
        self.cost_base: Optional[float] = None
        self._price: Dict[str, tk.StringVar] = {}
        self._sell: Dict[str, tk.BooleanVar] = {}
        self._dirty: set = set()           # niveles con precio escrito por el usuario
        self._levels: List[str] = []
        self._hints: Dict[str, ttk.Label] = {}
        self.columnconfigure(1, weight=1)

    # -- construcción ---------------------------------------------------------------
    def refresh(self) -> None:
        """Reconstruye las filas según los niveles que existen hoy (conserva lo ya escrito)."""
        try:
            product = self.provider()
        except ValueError:
            return
        levels = unit_levels(product)
        if levels != self._levels or any(self._label_changed(product, lvl) for lvl in levels):
            self._levels = levels
            self._rebuild(product)
        self._update_hints()

    def _label_changed(self, product: Dict, level: str) -> bool:
        return self._current_labels.get(level) != level_label(product, level) if hasattr(self, "_current_labels") else True

    def _rebuild(self, product: Dict) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._hints.clear()
        self._current_labels = {lvl: level_label(product, lvl) for lvl in self._levels}
        defaults = default_sellable(product)
        ttk.Label(self, text="Se vende por", style=self._muted_style).grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(self, text="Precio (S/)", style=self._muted_style).grid(row=0, column=1, sticky="w")
        for row, level in enumerate(reversed(self._levels), start=1):
            sell = self._sell.setdefault(level, tk.BooleanVar(value=level in defaults))
            price = self._price.setdefault(level, tk.StringVar())
            ttk.Checkbutton(self, text=self._current_labels[level], variable=sell, style=self._check_style).grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 16))
            entry = ttk.Entry(self, textvariable=price, width=10, justify="right")
            entry.grid(row=row, column=1, sticky="w", pady=3)
            entry.bind("<KeyRelease>", lambda _e, lvl=level: self._on_typed(lvl))
            hint = ttk.Label(self, style=self._muted_style)
            hint.grid(row=row, column=2, sticky="w", padx=12)
            self._hints[level] = hint

    # -- comportamiento ---------------------------------------------------------------
    def _on_typed(self, level: str) -> None:
        self._dirty.add(level) if self._price[level].get().strip() else self._dirty.discard(level)
        self._suggest_others()
        self._update_hints()

    def _top_price(self) -> Optional[float]:
        try:
            return float(self._price[self._levels[-1]].get())
        except (KeyError, ValueError, IndexError):
            return None

    def _suggest_others(self) -> None:
        """Con el precio del empaque ya escrito, rellena los demás niveles que el usuario no tocó."""
        top = self._top_price()
        if top is None:
            return
        hierarchy = self.provider()["unit_hierarchy"]
        for level in self._levels[:-1]:
            if level not in self._dirty:
                self._price[level].set(f"{suggested_price(top, hierarchy, level):.2f}")

    def set_cost_base(self, cost_base: Optional[float]) -> None:
        self.cost_base = cost_base
        self._update_hints()

    def _update_hints(self) -> None:
        for level, hint in self._hints.items():
            try:
                price = float(self._price[level].get())
            except ValueError:
                hint.configure(text="")
                continue
            if self.cost_base and price > 0:
                factor = unit_factor(self.provider()["unit_hierarchy"], level)
                margin = (price - self.cost_base * factor) / price
                hint.configure(text=f"margen {margin:.0%}",
                               foreground=THEME["success"] if margin >= 0.15 else THEME["warning"])
            else:
                hint.configure(text="")

    # -- datos ------------------------------------------------------------------------
    def load(self, prices: Dict[str, float], sellable: List[str]) -> None:
        """Muestra los precios y las unidades de venta de un producto existente."""
        self.refresh()
        self._dirty = set(prices)
        for level in self._levels:
            self._price[level].set(f"{prices[level]:.2f}" if level in prices else "")
            self._sell[level].set(level in sellable)
        self._suggest_others()
        self._update_hints()

    def reset(self) -> None:
        """Vacía los precios y vuelve a las unidades de venta por defecto de la presentación actual."""
        self._dirty.clear()
        self.refresh()
        for level in self._levels:
            self._price[level].set("")
        self.reset_sellable()

    def reset_sellable(self) -> None:
        """Marca solo las unidades en que normalmente se vende este tipo de producto."""
        self.refresh()
        try:
            defaults = default_sellable(self.provider())
        except ValueError:
            return
        for level in self._levels:
            self._sell[level].set(level in defaults)

    def values(self) -> Tuple[Dict[str, float], List[str]]:
        """(precios por nivel, niveles vendibles). Lanza ValueError con un mensaje para el usuario."""
        self.refresh()
        sellable = [lvl for lvl in self._levels if self._sell[lvl].get()]
        if not sellable:
            raise ValueError("Marca al menos una unidad en la que se venderá el producto.")
        prices: Dict[str, float] = {}
        for level in self._levels:
            text = self._price[level].get().strip()
            if text:
                try:
                    prices[level] = money(float(text))
                except ValueError:
                    raise ValueError("Los precios deben ser números (ej. 2.50).") from None
            elif level in sellable:
                raise ValueError(f"Falta el precio de venta por {self._current_labels[level]}.")
        return prices, sellable
