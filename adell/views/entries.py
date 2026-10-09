import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import Dict, Optional
from uuid import uuid4

from adell.domain import (DATE_FMT, PRESENTATIONS, format_quantity, format_stock_display, money, parse_date,
                          today_str, unit_choices, unit_factor, units_per_package)
from adell.store import DataStore
from adell.ui.theme import THEME, display_font, ui_font
from adell.ui.price_grid import PriceGrid, hierarchy_from_vars
from adell.ui.widgets import (Button, QuantityStepper, ScrollableFrame, SegmentedControl, build_tree,
                              page_header, stripe_tree)

# Configuración sugerida de unidades por presentación:
# (unidad base, empaque intermedio, unidades por intermedio, intermedios por paquete,
#  mostrar bloque de empaque, etiquetas de los cuatro campos, ayuda)
_CAJA_LABELS = ("Unidad mínima (Tableta, cápsula)", "Empaque (Blister, sobre)", "Unidades por empaque", "Empaques por caja")
_MEDIDA_LABELS = ("Medida (ml, g)", "(No aplica)", "(No aplica)", "Contenido total")
PRESETS = {
    "Caja": ("Tableta", "Blister", "10", "2", True, _CAJA_LABELS,
             "Una caja con 2 blisters de 10 tabletas contiene 20 tabletas."),
    "Frasco": ("ml", "", "1", "120", True, _MEDIDA_LABELS, "Un frasco de jarabe suele contener 120 ml."),
    "Botella": ("ml", "", "1", "500", True, _MEDIDA_LABELS, "Una botella de suero suele contener 500 ml."),
    "Blister": ("Tableta", "", "1", "10", False, None, "Un blister normalmente contiene 10 tabletas."),
    "Tableta": ("Tableta", "", "1", "1", False, None, "Venta por tableta individual."),
    "Unidad": ("Unidad", "", "1", "1", False, None, "Venta por unidad individual."),
    "Inhalador": ("Dosis", "", "1", "200", False, None, "Un inhalador normalmente contiene 200 dosis."),
}
_DEFAULT_PRESET = ("Unidad", "", "1", "1", False, None, "Configuración básica aplicada.")
UNIT_KEYS = ("base_unit", "intermediate_unit", "units_per_intermediate", "intermediate_per_package")


class EntriesView(ttk.Frame):
    """Registro de entradas de mercadería: suma stock a un producto existente o da de alta uno nuevo.

    Izquierda: elegir el producto (tabla) o describir el producto nuevo (formulario).
    Derecha: datos de la entrada (cantidad, unidad, fecha, notas). Abajo: historial reciente.
    """

    def __init__(self, parent, repo: DataStore, refresh_callback, app=None) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.repo = repo
        self.refresh_callback = refresh_callback
        self.app = app
        self.vars: Dict[str, tk.StringVar] = {}
        self.widgets: Dict[str, tk.Widget] = {}
        self.mode = tk.StringVar(value="existente")
        self.selected_product_id: Optional[str] = None
        self._unit_types: Dict[str, str] = {}
        self._applying_preset = False
        self._search_job = None
        self._scroll = ScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True)
        self._build(self._scroll.body)
        self._on_mode_change()
        self.refresh_data()

    # -- construcción -----------------------------------------------------------
    def _build(self, body) -> None:
        body.columnconfigure(0, weight=1)
        page_header(body, "Entradas", "Suma stock a un producto existente o registra uno nuevo.").grid(
            row=0, column=0, sticky="ew", pady=(0, 16))
        SegmentedControl(body, [("existente", "Producto existente"), ("nuevo", "Producto nuevo")],
                         self.mode, self._on_mode_change).grid(row=1, column=0, sticky="w", pady=(0, 16))

        work = ttk.Frame(body, style="Main.TFrame")
        work.grid(row=2, column=0, sticky="ew")
        work.columnconfigure(0, weight=1)
        work.columnconfigure(1, weight=0, minsize=340)
        self.picker = self._build_picker(work)
        self.new_form = self._build_new_form(work)
        self._build_entry_panel(work).grid(row=0, column=1, sticky="nsew", padx=(20, 0))

        ttk.Label(body, text="Entradas recientes", font=display_font(15, "bold")).grid(
            row=3, column=0, sticky="w", pady=(24, 8))
        box, self.tree = build_tree(body, ("date", "product", "qty", "notes", "user"), height=6)
        box.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        for key, text, width, anchor in (("date", "Fecha", 100, "center"), ("product", "Producto", 220, "w"),
                                         ("qty", "Cantidad", 130, "center"), ("notes", "Notas", 260, "w"),
                                         ("user", "Registró", 110, "w")):
            self.tree.heading(key, text=text, anchor=anchor)
            self.tree.column(key, width=width, minwidth=70, stretch=True, anchor=anchor)

    def _build_picker(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Main.TFrame")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Buscar producto", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._debounced_search())
        ttk.Entry(frame, textvariable=self.search_var).grid(row=1, column=0, sticky="ew", pady=(4, 10))
        box, self.picker_tree = build_tree(frame, ("name", "stock", "expiry"), height=8)
        box.grid(row=2, column=0, sticky="ew")
        for key, text, width, anchor in (("name", "Producto", 260, "w"), ("stock", "Existencias", 110, "center"),
                                         ("expiry", "Vence", 100, "center")):
            self.picker_tree.heading(key, text=text, anchor=anchor)
            self.picker_tree.column(key, width=width, minwidth=70, stretch=True, anchor=anchor)
        self.picker_tree.bind("<<TreeviewSelect>>", self._on_pick)
        return frame

    def _field(self, parent, key: str, label: str, row: int, col: int, span: int = 1, combo=None) -> ttk.Label:
        """Campo con etiqueta arriba. Devuelve la etiqueta (algunas cambian según la presentación)."""
        caption = ttk.Label(parent, text=label, style="Field.TLabel")
        caption.grid(row=row * 2, column=col, columnspan=span, sticky="w", padx=6)
        var = self.vars[key] = tk.StringVar()
        widget = (ttk.Combobox(parent, textvariable=var, values=combo, state="readonly") if combo
                  else ttk.Entry(parent, textvariable=var))
        widget.grid(row=row * 2 + 1, column=col, columnspan=span, sticky="ew", padx=6, pady=(2, 10))
        self.widgets[key] = widget
        return caption

    def _build_new_form(self, parent) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=20)
        for c in range(3):
            card.columnconfigure(c, weight=1, uniform="nf")
        ttk.Label(card, text="Datos del producto", font=display_font(14, "bold"), style="Card.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        f = lambda *a, **k: self._field(card, *a, **k)
        f("commercial_name", "Nombre comercial", 1, 0, 2)
        f("presentation", "Presentación", 1, 2, combo=PRESENTATIONS)
        f("generic_name", "Nombre genérico", 2, 0)
        f("laboratory", "Laboratorio", 2, 1)
        f("concentration_mg", "Concentración (mg)", 2, 2)
        f("expiry_date", "Vencimiento (AAAA-MM-DD)", 3, 0)
        f("therapeutic_action", "Acción terapéutica", 3, 1, 2)
        f("description", "Descripción", 4, 0, 3)

        # Bloque de empaque: solo se muestra para presentaciones compuestas (Caja, Frasco, Botella)
        self.units_block = ttk.Frame(card, style="CardInner.TFrame")
        self.units_block.grid(row=22, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.units_block, text="Unidades y empaque", font=ui_font(11, "bold"), style="Card.TLabel").pack(
            anchor="w", pady=(8, 8))
        unit_fields = ttk.Frame(self.units_block, style="CardInner.TFrame")
        unit_fields.pack(fill="x")
        for c in range(4):
            unit_fields.columnconfigure(c, weight=1, uniform="u")
        self.unit_captions = [self._field(unit_fields, key, key, 0, i) for i, key in enumerate(UNIT_KEYS)]
        self.preset_help = ttk.Label(card, style="CardMuted.TLabel")
        self.preset_help.grid(row=23, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 2))

        ttk.Label(card, text="Precios de venta", font=ui_font(11, "bold"), style="Card.TLabel").grid(
            row=24, column=0, columnspan=3, sticky="w", pady=(10, 6))
        self.price_grid = PriceGrid(card, lambda: hierarchy_from_vars(self.vars), surface=True)
        self.price_grid.grid(row=25, column=0, columnspan=3, sticky="w", padx=6)

        self.vars["presentation"].trace_add("write", lambda *_: self._apply_preset())
        for key in UNIT_KEYS + ("presentation",):
            self.vars[key].trace_add("write", lambda *_: self._refresh_units())
        for key in ("units_per_intermediate", "intermediate_per_package"):
            self.vars[key].trace_add("write", lambda *_: self._update_margin_base())
        self._reset_new_form()
        return card

    def _build_entry_panel(self, parent) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=22)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="Producto", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.target_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.target_var, font=display_font(16, "bold"), style="Card.TLabel",
                  wraplength=290).grid(row=1, column=0, sticky="w", pady=(2, 2))
        self.stock_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.stock_var, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 18))

        ttk.Label(panel, text="Cantidad que ingresa", style="Field.TLabel").grid(row=3, column=0, sticky="w")
        self.vars["quantity"] = tk.StringVar(value="1")
        QuantityStepper(panel, self.vars["quantity"]).grid(row=4, column=0, sticky="ew", pady=(4, 14))

        ttk.Label(panel, text="Ingresa por", style="Field.TLabel").grid(row=5, column=0, sticky="w")
        self.vars["unit_type"] = tk.StringVar()
        self.unit_combo = ttk.Combobox(panel, textvariable=self.vars["unit_type"], state="readonly")
        self.unit_combo.grid(row=6, column=0, sticky="ew", pady=(4, 14))

        self.cost_caption = tk.StringVar(value="Precio de compra por unidad (S/)")
        ttk.Label(panel, textvariable=self.cost_caption, style="Field.TLabel").grid(row=7, column=0, sticky="w")
        self.vars["cost"] = tk.StringVar()
        ttk.Entry(panel, textvariable=self.vars["cost"]).grid(row=8, column=0, sticky="ew", pady=(4, 14))

        ttk.Label(panel, text="Fecha (AAAA-MM-DD)", style="Field.TLabel").grid(row=9, column=0, sticky="w")
        self.vars["entry_date"] = tk.StringVar(value=today_str())
        ttk.Entry(panel, textvariable=self.vars["entry_date"]).grid(row=10, column=0, sticky="ew", pady=(4, 14))

        ttk.Label(panel, text="Notas (opcional)", style="Field.TLabel").grid(row=11, column=0, sticky="w")
        self.vars["notes"] = tk.StringVar()
        ttk.Entry(panel, textvariable=self.vars["notes"]).grid(row=12, column=0, sticky="ew", pady=(4, 16))

        ttk.Frame(panel, style="Rule.TFrame", height=1).grid(row=13, column=0, sticky="ew")
        total_row = ttk.Frame(panel, style="CardInner.TFrame")
        total_row.grid(row=14, column=0, sticky="ew", pady=(10, 14))
        ttk.Label(total_row, text="Inversión", style="CardMuted.TLabel").pack(side="left")
        self.total_var = tk.StringVar(value="S/ 0.00")
        ttk.Label(total_row, textvariable=self.total_var, style="Card.TLabel", font=ui_font(18, "bold")).pack(side="right")

        self.btn_register = Button(panel, text="Registrar entrada", variant="primary", command=self._register)
        self.btn_register.grid(row=15, column=0, sticky="ew")
        Button(panel, text="Limpiar", command=self._clear_form).grid(row=16, column=0, sticky="ew", pady=(8, 0))

        self.vars["cost"].trace_add("write", lambda *_: (self._update_total(), self._update_margin_base()))
        self.vars["quantity"].trace_add("write", lambda *_: self._update_total())
        self.vars["unit_type"].trace_add("write", lambda *_: self._on_unit_change())
        return panel

    # -- modo y selección ---------------------------------------------------------
    def _on_mode_change(self) -> None:
        if self.mode.get() == "existente":
            self.new_form.grid_remove()
            self.picker.grid(row=0, column=0, sticky="nsew")
            self._refresh_picker()
            self._on_pick()
        else:
            self.picker.grid_remove()
            self.new_form.grid(row=0, column=0, sticky="nsew")
            self.target_var.set("Producto nuevo")
            self.stock_var.set("Se creará con las existencias de esta entrada.")
            self.vars["cost"].set("")
            self._refresh_units()
        self._update_register_state()

    def _debounced_search(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self._refresh_picker)

    def _refresh_picker(self) -> None:
        self._search_job = None
        self.picker_tree.delete(*self.picker_tree.get_children())
        for p in self.repo.search_products(self.search_var.get(), sort_by_expiry=False):
            self.picker_tree.insert("", "end", iid=p["id"], values=(
                p["commercial_name"], format_stock_display(p), p["expiry_date"]))
        stripe_tree(self.picker_tree, empty_text="Ningún producto coincide con la búsqueda")
        if self.selected_product_id and self.picker_tree.exists(self.selected_product_id):
            self.picker_tree.selection_set(self.selected_product_id)

    def _on_pick(self, _event=None) -> None:
        if self.mode.get() != "existente":
            return
        selection = self.picker_tree.selection()
        product = self.repo.get_product(selection[0]) if selection else None
        self.selected_product_id = product["id"] if product else None
        if not product:
            self.target_var.set("Selecciona un producto")
            self.stock_var.set("")
            self._set_units({})
        else:
            self.target_var.set(product["commercial_name"])
            self.stock_var.set(f"Existencias actuales: {format_stock_display(product)}")
            self._set_units(unit_choices(product))
            self._prefill_cost()
        self._update_register_state()

    def _update_register_state(self) -> None:
        ready = self.mode.get() == "nuevo" or self.selected_product_id is not None
        self.btn_register.configure(state="normal" if ready else "disabled")

    def _set_units(self, choices: Dict[str, str]) -> None:
        """Las compras se hacen normalmente por el empaque completo: es la unidad que se propone."""
        self._unit_types = choices
        self.unit_combo.configure(values=list(choices))
        if self.vars["unit_type"].get() not in choices:
            self.vars["unit_type"].set(next(reversed(choices), ""))
        self._on_unit_change()

    def _current_hierarchy(self) -> Dict:
        """Jerarquía del producto que se está moviendo (el elegido o el que se está describiendo)."""
        if self.mode.get() == "existente":
            product = self.repo.get_product(self.selected_product_id) if self.selected_product_id else None
            return (product or {}).get("unit_hierarchy", {})
        return hierarchy_from_vars(self.vars)["unit_hierarchy"]

    def _on_unit_change(self) -> None:
        label = self.vars["unit_type"].get() or "unidad"
        self.cost_caption.set(f"Precio de compra por {label.lower()} (S/)")
        self._prefill_cost()
        self._update_total()

    def _prefill_cost(self) -> None:
        """En un producto existente propone el último costo, convertido a la unidad elegida."""
        if self.mode.get() != "existente" or not self.selected_product_id:
            return
        product = self.repo.get_product(self.selected_product_id)
        level = self._unit_types.get(self.vars["unit_type"].get())
        if not product or not level:
            return
        per_base = product.get("avg_cost_base", 0.0)
        cost = per_base * unit_factor(product.get("unit_hierarchy", {}), level)
        self.vars["cost"].set(f"{cost:.2f}" if cost else "")

    def _update_total(self) -> None:
        try:
            self.total_var.set(f"S/ {money(int(self.vars['quantity'].get()) * float(self.vars['cost'].get() or 0)):.2f}")
        except ValueError:
            self.total_var.set("S/ 0.00")

    def _update_margin_base(self) -> None:
        """Costo por unidad base (para los márgenes del producto nuevo) a partir de lo que cuesta la unidad de compra."""
        if self.mode.get() != "nuevo":
            return
        try:
            level = self._unit_types.get(self.vars["unit_type"].get())
            cost = float(self.vars["cost"].get() or 0)
            factor = unit_factor(self._current_hierarchy(), level) if level else 0
        except ValueError:
            return
        self.price_grid.set_cost_base(cost / factor if cost > 0 and factor else None)

    # -- producto nuevo: presets de empaque -----------------------------------------
    def _apply_preset(self) -> None:
        """Rellena el empaque típico de la presentación elegida (el usuario puede ajustarlo después)."""
        presentation = self.vars["presentation"].get()
        base, inter, upi, ipp, show_units, labels, help_text = PRESETS.get(presentation, _DEFAULT_PRESET)
        self._applying_preset = True
        try:
            for key, value in zip(UNIT_KEYS, (base, inter, upi, ipp)):
                self.vars[key].set(value)
        finally:
            self._applying_preset = False
        if show_units:
            self.units_block.grid()
            for caption, text in zip(self.unit_captions, labels):
                caption.configure(text=text)
            for key in ("intermediate_unit", "units_per_intermediate"):
                self.widgets[key].configure(state="normal" if inter else "disabled")
        else:
            self.units_block.grid_remove()
        self.preset_help.configure(text=help_text)
        self._refresh_units()
        self.price_grid.reset_sellable()

    def _refresh_units(self) -> None:
        """Actualiza las unidades de ingreso según el producto nuevo que se está describiendo."""
        if self._applying_preset or self.mode.get() != "nuevo":
            return
        try:
            pseudo = hierarchy_from_vars(self.vars)
        except ValueError:
            return  # el usuario está escribiendo un número a medias
        self._set_units(unit_choices(pseudo))
        self.price_grid.refresh()
        self._update_margin_base()

    def _reset_new_form(self) -> None:
        for key in ("commercial_name", "generic_name", "laboratory", "concentration_mg",
                    "therapeutic_action", "description"):
            self.vars[key].set("")
        self.vars["expiry_date"].set((date.today() + timedelta(days=365)).strftime(DATE_FMT))
        self.vars["presentation"].set(PRESENTATIONS[0])
        self._apply_preset()
        self.price_grid.reset()

    def _clear_form(self) -> None:
        self.vars["quantity"].set("1")
        self.vars["entry_date"].set(today_str())
        self.vars["notes"].set("")
        self.vars["cost"].set("")
        self._reset_new_form()
        self._prefill_cost()

    # -- historial ----------------------------------------------------------------
    def refresh_data(self) -> None:
        self.tree.delete(*self.tree.get_children())
        entries = [m for m in self.repo.movements if m["type"] == "Entrada"]
        if self.app and self.app.current_user_type != "admin":
            entries = [m for m in entries if m.get("username") == self.app.current_user_type]
        for m in sorted(entries, key=lambda x: (x["date"], x.get("recorded_at", "")), reverse=True)[:50]:
            product = self.repo.get_product(m["product_id"])
            quantity = format_quantity(product, m.get("unit_type", "base_unit"), m["quantity"]) if product else str(m["quantity"])
            self.tree.insert("", "end", values=(m["date"], m.get("product_name") or (product or {}).get("commercial_name", "—"),
                                                quantity, m.get("notes", ""), m.get("user_display_name", "")))
        stripe_tree(self.tree, empty_text="Aún no hay entradas registradas")
        if self.mode.get() == "existente":
            self._refresh_picker()
            self._on_pick()

    # -- registro -----------------------------------------------------------------
    def _new_product(self) -> Optional[Dict]:
        """Valida el formulario de producto nuevo y arma el producto (stock 0). None si hay un error (ya avisado)."""
        v = {k: var.get().strip() for k, var in self.vars.items()}
        if not v["commercial_name"]:
            messagebox.showerror("Falta el nombre", "El nombre comercial es obligatorio.")
            return None
        if any(p["commercial_name"].lower() == v["commercial_name"].lower() for p in self.repo.products):
            messagebox.showwarning("Producto repetido", f"«{v['commercial_name']}» ya existe. "
                                   "Usa «Producto existente» para sumarle stock.")
            return None
        try:
            parse_date(v["expiry_date"])
            hierarchy = hierarchy_from_vars(self.vars)["unit_hierarchy"]
            presentation = v["presentation"] or PRESENTATIONS[0]
            prices, sellable = self.price_grid.values()
            product = {
                "id": str(uuid4()), "commercial_name": v["commercial_name"], "generic_name": v["generic_name"],
                "laboratory": v["laboratory"], "therapeutic_action": v["therapeutic_action"],
                "description": v["description"], "presentation": presentation,
                "package_units": units_per_package(hierarchy),
                "concentration_mg": int(float(v["concentration_mg"] or 0)),
                "stock": 0,  # record_movement suma la cantidad de esta entrada
                "expiry_date": v["expiry_date"],
                "unit_hierarchy": {**hierarchy, "total_base_units": 0},
                "prices": prices, "sellable_units": sellable, "avg_cost_base": 0.0, "cost_per_package": 0.0,
                "pricing_version": 2, "needs_price_review": False,
            }
        except ValueError as error:
            text = str(error)
            messagebox.showerror("Revisa los datos", text if text.startswith(("Marca", "Falta", "Los precios")) else
                                 "El vencimiento debe ser AAAA-MM-DD y la concentración y las cantidades deben ser números.")
            return None
        return product

    def _register(self) -> None:
        try:
            qty = int(self.vars["quantity"].get() or "0")
            if qty <= 0:
                raise ValueError()
            parse_date(self.vars["entry_date"].get())
            unit_cost = float(self.vars["cost"].get() or 0)
            if unit_cost < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Datos inválidos", "La cantidad debe ser un entero positivo, el precio de compra un "
                                 "número y la fecha AAAA-MM-DD.")
            return

        creating = self.mode.get() == "nuevo"
        if creating:
            product = self._new_product()
            if product is None:
                return
        else:
            product = self.repo.get_product(self.selected_product_id) if self.selected_product_id else None
            if not product:
                messagebox.showerror("Falta el producto", "Selecciona un producto de la tabla.")
                return
        if unit_cost == 0 and not messagebox.askyesno(
                "Sin precio de compra", "El precio de compra es 0: la inversión y el costo del producto quedarán "
                "en cero. ¿Registrar de todos modos?"):
            return
        if creating:
            self.repo.upsert_product(product)

        unit_type = self._unit_types.get(self.vars["unit_type"].get(), "base_unit")
        unit_display = format_quantity(product, unit_type, qty)
        movement = {
            "id": str(uuid4()), "product_id": product["id"], "product_name": product["commercial_name"],
            "type": "Entrada", "quantity": qty, "unit_type": unit_type, "unit_price": unit_cost,
            "date": self.vars["entry_date"].get(), "notes": self.vars["notes"].get().strip(),
            "recorded_at": datetime.now().isoformat(),
            "username": self.app.current_user_type if self.app else "admin",
            "user_display_name": self.app.current_user_name if self.app else "Admin",
        }
        try:
            self.repo.record_movement(movement)
            if self.app and self.app.current_user_type != "admin":
                self.repo.log_activity(
                    username=self.app.current_user_type, user_name=self.app.current_user_name,
                    action="Registro de Entrada",
                    details={"product_name": product["commercial_name"], "quantity": unit_display,
                             "movement_type": "Entrada", "total": movement["line_total"],
                             "date": self.vars["entry_date"].get()})
        except ValueError as e:
            messagebox.showerror("Error", f"No se pudo registrar la entrada: {e}")
            return

        title, text = (("Producto creado", "Producto creado y entrada registrada:\n") if creating
                       else ("Entrada registrada", ""))
        messagebox.showinfo(title, f"{text}{unit_display} de {product['commercial_name']}\n"
                            f"Inversión: S/ {movement['line_total']:.2f}")
        self._clear_form()
        self.refresh_callback()
