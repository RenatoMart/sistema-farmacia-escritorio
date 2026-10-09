import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk
from typing import Dict, Optional, Tuple
from uuid import uuid4

from adell.domain import (DATE_FMT, PRESENTATIONS, format_stock_display, parse_date, price_summary,
                          sellable_levels, today_str, units_per_package)
from adell.store import DataStore
from adell.ui.price_grid import PriceGrid, hierarchy_from_vars
from adell.ui.theme import THEME, display_font, ui_font
from adell.ui.widgets import Button, ModalDialog, StatStrip, build_tree, page_header, stripe_tree

STATUS_FILTERS = ("Todos", "Vencidos", "Por vencer", "Vigentes", "Sin stock", "Precios por revisar")


def expiry_status(product: Dict, today: date, alert_days: int) -> Tuple[str, str, str]:
    """Clasifica un producto por vencimiento y stock.

    Devuelve (clave del filtro, texto para la tabla, etiqueta de color de `build_tree`).
    Un producto sin stock no se considera vencido ni por vencer: no hay nada que retirar.
    """
    if product["stock"] <= 0:
        return "Sin stock", "Sin stock", "muted"
    days = (parse_date(product["expiry_date"]) - today).days
    if days < 0:
        return "Vencidos", f"Vencido hace {-days} d", "expired"
    if days <= alert_days:
        return "Por vencer", f"Vence en {days} d", "expiring"
    return "Vigentes", "Vigente", ""


class ProductDialog(ModalDialog):
    """Formulario modal para crear o editar un producto. `saved` indica si se guardó."""

    GENERAL = (
        ("commercial_name", "Nombre comercial", 0, 0, 1),
        ("generic_name", "Nombre genérico", 0, 1, 1),
        ("laboratory", "Laboratorio", 0, 2, 1),
        ("presentation", "Presentación", 0, 3, 1),
        ("concentration_mg", "Concentración (mg)", 1, 0, 1),
        ("stock", "Existencias (unidades base)", 1, 1, 1),
        ("expiry_date", "Vencimiento (AAAA-MM-DD)", 1, 2, 1),
        ("cost_per_package", "Costo de compra por empaque (S/)", 1, 3, 1),
        ("therapeutic_action", "Acción terapéutica", 2, 0, 2),
        ("description", "Descripción", 2, 2, 2),
    )
    PACKAGING = (
        ("base_unit", "Unidad mínima (Tableta, ml)", 0, 0, 2),
        ("intermediate_unit", "Empaque (Blister, sobre)", 0, 1, 2),
        ("units_per_intermediate", "Unidades por empaque", 1, 0, 2),
        ("intermediate_per_package", "Empaques por caja", 1, 1, 2),
    )

    def __init__(self, parent, repo: DataStore, product: Optional[Dict] = None) -> None:
        super().__init__(parent, "Editar producto" if product else "Nuevo producto", 940, 640)
        self.repo = repo
        self.product = product
        self.product_id = product["id"] if product else None
        self.saved = False
        self.vars: Dict[str, tk.StringVar] = {}
        self._build(product)

    def _build(self, product: Optional[Dict]) -> None:
        body = self.body
        for c in range(4):
            body.columnconfigure(c, weight=1, uniform="f")

        title = "Editar producto" if product else "Nuevo producto"
        ttk.Label(body, text=title, font=display_font(20, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Frame(body, style="Rule.TFrame", height=1).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 12))

        self._section(body, "Datos generales", 2)
        self._fields(body, self.GENERAL, body, first_row=3)

        # Unidades (izquierda) y precios de venta (derecha)
        lower = ttk.Frame(body, style="Main.TFrame")
        lower.grid(row=10, column=0, columnspan=4, sticky="nsew", pady=(6, 0))
        lower.columnconfigure(0, weight=1, uniform="l")
        lower.columnconfigure(1, weight=1, uniform="l")
        left = ttk.Frame(lower, style="Main.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left.columnconfigure(0, weight=1, uniform="p")
        left.columnconfigure(1, weight=1, uniform="p")
        self._section(left, "Unidades y empaque", 0, span=2)
        self._fields(left, self.PACKAGING, left, first_row=1)
        ttk.Label(left, style="Muted.TLabel", wraplength=380, text="Ej.: una caja con 2 blisters de 10 cápsulas "
                  "= 20 unidades base. Deja el empaque vacío si no hay blister.").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=6)

        right = ttk.Frame(lower, style="Main.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        self._section(right, "Precios de venta", 0)
        self.price_grid = PriceGrid(right, lambda: hierarchy_from_vars(self.vars), surface=False)
        self.price_grid.grid(row=1, column=0, sticky="w", padx=6)

        footer = ttk.Frame(body, style="Main.TFrame")
        footer.grid(row=20, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        self.error_var = tk.StringVar()
        ttk.Label(footer, textvariable=self.error_var, foreground=THEME["danger"]).pack(side="left")
        Button(footer, text="Guardar producto", variant="primary", command=self._save).pack(side="right")
        Button(footer, text="Cancelar", command=self.destroy).pack(side="right", padx=10)

        self._load(product)
        for key in ("presentation", "base_unit", "intermediate_unit", "units_per_intermediate",
                    "intermediate_per_package"):
            self.vars[key].trace_add("write", lambda *_: self.price_grid.refresh())
        for key in ("cost_per_package", "units_per_intermediate", "intermediate_per_package"):
            self.vars[key].trace_add("write", lambda *_: self._update_cost())
        self._update_cost()

    @staticmethod
    def _section(parent, text: str, row: int, span: int = 4) -> None:
        ttk.Label(parent, text=text, font=ui_font(11, "bold")).grid(row=row, column=0, columnspan=span, sticky="w",
                                                                   pady=(6, 6))

    def _fields(self, parent, spec, grid_parent, first_row: int) -> None:
        for key, label, row, col, span in spec:
            r = first_row + row * 2
            ttk.Label(parent, text=label, style="Muted.TLabel").grid(row=r, column=col, columnspan=span, sticky="w", padx=6)
            var = self.vars[key] = tk.StringVar()
            if key == "presentation":
                widget = ttk.Combobox(parent, textvariable=var, values=PRESENTATIONS, state="readonly")
            else:
                widget = ttk.Entry(parent, textvariable=var)
            widget.grid(row=r + 1, column=col, columnspan=span, sticky="ew", padx=6, pady=(2, 8))

    def _update_cost(self) -> None:
        """Costo por unidad base a partir del costo por empaque, para mostrar márgenes."""
        try:
            hierarchy = hierarchy_from_vars(self.vars)["unit_hierarchy"]
            cost = float(self.vars["cost_per_package"].get() or 0)
        except ValueError:
            return
        self.price_grid.set_cost_base(cost / units_per_package(hierarchy) if cost > 0 else None)

    def _load(self, product: Optional[Dict]) -> None:
        if product is None:
            self.vars["presentation"].set(PRESENTATIONS[0])
            self.vars["expiry_date"].set((date.today() + timedelta(days=365)).strftime(DATE_FMT))
            self.vars["units_per_intermediate"].set("1")
            self.vars["intermediate_per_package"].set("1")
            self.price_grid.refresh()
            return
        hierarchy = product.get("unit_hierarchy", {})
        for key, var in self.vars.items():
            var.set(str(product.get(key, hierarchy.get(key, "")) or ""))
        self.price_grid.load(product.get("prices", {}), sellable_levels(product))

    def _save(self) -> None:
        v = {key: var.get().strip() for key, var in self.vars.items()}
        try:
            parse_date(v["expiry_date"] or today_str())
            hierarchy = hierarchy_from_vars(self.vars)["unit_hierarchy"] if v["base_unit"] else None
            presentation = v["presentation"] or PRESENTATIONS[0]
            cost_package = float(v["cost_per_package"] or 0.0)
            payload = {
                "id": self.product_id or str(uuid4()),
                "commercial_name": v["commercial_name"] or "Sin nombre",
                "generic_name": v["generic_name"],
                "laboratory": v["laboratory"],
                "therapeutic_action": v["therapeutic_action"],
                "description": v["description"],
                "presentation": presentation,
                "package_units": units_per_package(hierarchy) if hierarchy else 1,
                "concentration_mg": int(float(v["concentration_mg"] or 0)),
                "stock": int(float(v["stock"] or 0)),
                "expiry_date": v["expiry_date"] or today_str(),
                "needs_price_review": False,
            }
            if hierarchy:
                hierarchy["total_base_units"] = payload["stock"]
                payload["unit_hierarchy"] = hierarchy
            prices, sellable = self.price_grid.values()
        except ValueError as error:
            self.error_var.set(str(error) if "Marca" in str(error) or "Falta" in str(error) or "precios" in str(error)
                               else "Revisa los datos: fecha AAAA-MM-DD y números en stock, costo y cantidades.")
            return
        payload["prices"], payload["sellable_units"] = prices, sellable
        previous_cost = float((self.product or {}).get("cost_per_package", 0.0))
        if cost_package != previous_cost or not self.product:
            upp = units_per_package(hierarchy) if hierarchy else 1
            payload["cost_per_package"] = cost_package
            payload["avg_cost_base"] = round(cost_package / upp, 6)  # corrección manual del costo
        self.repo.upsert_product(payload)
        self.saved = True
        self.destroy()


class InventoryView(ttk.Frame):
    """Tabla de productos con filtros, indicadores y alta/edición/baja.

    La edición ocurre en `ProductDialog`; esta vista solo lista y filtra. Tras cualquier
    cambio llama a `refresh_callback` para que el resto de vistas se actualicen.
    """

    def __init__(self, parent, repo: DataStore, refresh_callback, app=None) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.repo = repo
        self.refresh_callback = refresh_callback
        self.app = app
        self.can_edit = not app or app.has_permission("edit_product")
        self._search_job = None
        self._build()
        self.refresh()

    # -- construcción -----------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        page_header(self, "Inventario", "Productos, existencias y fechas de vencimiento.").grid(
            row=0, column=0, sticky="ew", pady=(0, 16))

        self.stat_vars = {key: tk.StringVar(value="0") for key in ("total", "value", "expiring", "expired", "empty")}
        stats = [("Productos registrados", self.stat_vars["total"], "default"),
                 ("Valor del inventario (a costo)", self.stat_vars["value"], "default"),
                 ("Por vencer", self.stat_vars["expiring"], "warning"),
                 ("Vencidos con stock", self.stat_vars["expired"], "danger"),
                 ("Sin stock", self.stat_vars["empty"], "default")]
        if not self.can_edit:  # el personal de mostrador no ve costos
            stats.pop(1)
        StatStrip(self, stats).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Aviso tras migrar datos antiguos: los precios deben confirmarse una vez
        self.review_banner = tk.Frame(self, bg=THEME["danger_soft"])
        self.review_text = tk.StringVar()
        tk.Label(self.review_banner, textvariable=self.review_text, bg=THEME["danger_soft"], fg=THEME["danger"],
                 font=ui_font(10), anchor="w").pack(side="left", padx=14, pady=8)
        Button(self.review_banner, text="Confirmar todos", command=self._confirm_all, padx=12, pady=4).pack(
            side="right", padx=(0, 10), pady=6)
        Button(self.review_banner, text="Ver productos", command=self._show_review, padx=12, pady=4).pack(
            side="right", padx=10, pady=6)

        toolbar = ttk.Frame(self, style="Main.TFrame")
        toolbar.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)

        filters = ttk.Frame(toolbar, style="Main.TFrame")
        filters.grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.presentation_var = tk.StringVar(value="Todos")
        self.status_var = tk.StringVar(value="Todos")
        ttk.Label(filters, text="Buscar", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.search_var, width=32).grid(row=1, column=0, padx=(0, 12))
        ttk.Label(filters, text="Presentación", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(filters, textvariable=self.presentation_var, values=["Todos"] + PRESENTATIONS,
                     state="readonly", width=14).grid(row=1, column=1, padx=(0, 12))
        ttk.Label(filters, text="Estado", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Combobox(filters, textvariable=self.status_var, values=STATUS_FILTERS,
                     state="readonly", width=14).grid(row=1, column=2)
        for var in (self.search_var, self.presentation_var, self.status_var):
            var.trace_add("write", lambda *_: self._debounced_refresh())

        actions = ttk.Frame(toolbar, style="Main.TFrame")
        actions.grid(row=0, column=1, sticky="se")
        if self.can_edit:
            self.btn_delete = Button(actions, text="Eliminar", variant="danger", state="disabled", command=self._delete)
            self.btn_delete.pack(side="right")
            self.btn_edit = Button(actions, text="Editar", state="disabled", command=self._edit)
            self.btn_edit.pack(side="right", padx=8)
            Button(actions, text="Nuevo producto", variant="primary", command=self._new).pack(side="right")
        else:
            ttk.Label(actions, text="Solo el administrador puede modificar productos", style="Muted.TLabel").pack()

        columns = ("commercial", "generic", "presentation", "sale", "stock", "expiry", "status")
        box, self.tree = build_tree(self, columns, height=12)
        box.grid(row=4, column=0, sticky="nsew")
        self.default_col_widths = {"commercial": 200, "generic": 170, "presentation": 100, "sale": 165,
                                   "stock": 230, "expiry": 100, "status": 140}
        headings = {"commercial": "Producto", "generic": "Nombre genérico", "presentation": "Presentación",
                    "sale": "Precio", "stock": "Existencias", "expiry": "Vence", "status": "Estado"}
        aligns = {"commercial": "w", "generic": "w", "sale": "e", "stock": "w", "status": "w"}
        for key, label in headings.items():
            anchor = aligns.get(key, "center")
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.default_col_widths[key], minwidth=70, stretch=True, anchor=anchor)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        if self.can_edit:
            self.tree.bind("<Double-1>", lambda _e: self._edit())

    # -- datos ------------------------------------------------------------------
    def _debounced_refresh(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.refresh)

    def refresh(self) -> None:
        """Recarga tabla e indicadores desde el repositorio respetando los filtros."""
        self._search_job = None
        today = date.today()
        alert_days = self.repo.settings.get("upcoming_days", 60)

        counts = {"Vencidos": 0, "Por vencer": 0, "Sin stock": 0}
        inventory_value = 0.0
        for product in self.repo.products:
            key = expiry_status(product, today, alert_days)[0]
            if key in counts:
                counts[key] += 1
            inventory_value += product["stock"] * product.get("avg_cost_base", 0.0)
        to_review = sum(1 for p in self.repo.products if p.get("needs_price_review"))
        if to_review:
            self.review_text.set(f"{to_review} productos migrados necesitan confirmar sus precios y costos "
                                 "(revísalos con «Editar» o confirma todos).")
            self.review_banner.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        else:
            self.review_banner.grid_remove()
        self.stat_vars["value"].set(f"S/ {inventory_value:,.2f}")
        self.stat_vars["total"].set(str(len(self.repo.products)))
        self.stat_vars["expiring"].set(str(counts["Por vencer"]))
        self.stat_vars["expired"].set(str(counts["Vencidos"]))
        self.stat_vars["empty"].set(str(counts["Sin stock"]))

        previous = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        wanted = self.status_var.get()
        special: Dict[str, str] = {}
        for product in self.repo.search_products(self.search_var.get(), self.presentation_var.get(), sort_by_expiry=True):
            key, text, tag = expiry_status(product, today, alert_days)
            if wanted == "Precios por revisar":
                if not product.get("needs_price_review"):
                    continue
            elif wanted != "Todos" and key != wanted:
                continue
            if tag:
                special[product["id"]] = tag
            self.tree.insert("", "end", iid=product["id"], values=(
                product["commercial_name"], product["generic_name"], product["presentation"],
                price_summary(product), format_stock_display(product), product["expiry_date"], text))
        stripe_tree(self.tree, special, empty_text="Ningún producto coincide con los filtros")
        if previous and self.tree.exists(previous[0]):
            self.tree.selection_set(previous[0])
        self._on_select()

    # -- acciones ---------------------------------------------------------------
    def _selected_product(self) -> Optional[Dict]:
        selection = self.tree.selection()
        return self.repo.get_product(selection[0]) if selection else None

    def _on_select(self, _event=None) -> None:
        if not self.can_edit:
            return
        state = "normal" if self.tree.selection() else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)

    def _open_editor(self, product: Optional[Dict]) -> None:
        dialog = ProductDialog(self, self.repo, product)
        dialog.run()
        if dialog.saved:
            self.refresh_callback()

    def _confirm_all(self) -> None:
        if not messagebox.askyesno("Confirmar precios", "¿Dar por buenos los precios y costos migrados de todos los "
                                   "productos? Puedes corregir cualquiera después con «Editar».", parent=self):
            return
        for product in self.repo.products:
            product["needs_price_review"] = False
        self.repo.save_products()
        self.refresh()

    def _show_review(self) -> None:
        self.status_var.set("Precios por revisar")

    def _new(self) -> None:
        self._open_editor(None)

    def _edit(self) -> None:
        product = self._selected_product()
        if product:
            self._open_editor(product)

    def _delete(self) -> None:
        product = self._selected_product()
        if not product:
            return
        if not messagebox.askyesno("Eliminar producto", f"¿Eliminar «{product['commercial_name']}» del inventario?\n"
                                   "Sus movimientos históricos se conservan.", parent=self):
            return
        self.repo.delete_product(product["id"])
        self.refresh_callback()

    def _reset_columns(self) -> None:
        for key, width in self.default_col_widths.items():
            self.tree.column(key, width=width)
