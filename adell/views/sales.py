import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Dict, Optional
from uuid import uuid4

from adell.domain import (convert_units_to_base, format_quantity, format_stock_display, level_label, money,
                          parse_date, price_summary, resolve_price, today_str, unit_choices)
from adell.store import DataStore
from adell.ui.theme import THEME, display_font, ui_font
from adell.ui.widgets import Button, QuantityStepper, build_tree, page_header, stripe_tree


class SalesView(ttk.Frame):
    """Registro de salidas: se elige un producto de la tabla y se completa el panel de venta."""

    def __init__(self, parent, repo: DataStore, refresh_callback, app=None) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.repo = repo
        self.refresh_callback = refresh_callback
        self.app = app
        self.selected_product_id: Optional[str] = None
        self._unit_types: Dict[str, str] = {}
        self._search_job = None
        self._build()
        self.refresh_table()

    # -- construcción -----------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        page_header(self, "Salidas", "Elige un producto, indica la cantidad y registra la venta.").grid(
            row=0, column=0, sticky="ew", pady=(0, 16))

        main = ttk.Frame(self, style="Main.TFrame")
        main.grid(row=1, column=0, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0, minsize=340)

        # Izquierda: buscador + tabla
        left = ttk.Frame(main, style="Main.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Buscar producto", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._debounced_search())
        ttk.Entry(left, textvariable=self.search_var).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        box, self.tree = build_tree(left, ("name", "stock", "price"), height=14)
        box.grid(row=2, column=0, sticky="nsew")
        for key, text, width, anchor in (("name", "Producto", 240, "w"), ("stock", "Existencias", 250, "w"),
                                         ("price", "Precio", 130, "e")):
            self.tree.heading(key, text=text, anchor=anchor)
            self.tree.column(key, width=width, minwidth=80, stretch=True, anchor=anchor)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Derecha: panel de venta
        panel = ttk.Frame(main, style="Card.TFrame", padding=22)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Producto", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.selected_name_var = tk.StringVar(value="Selecciona un producto")
        ttk.Label(panel, textvariable=self.selected_name_var, font=display_font(16, "bold"), style="Card.TLabel",
                  wraplength=290).grid(row=1, column=0, sticky="w", pady=(2, 2))
        self.stock_display_var = tk.StringVar(value="")
        ttk.Label(panel, textvariable=self.stock_display_var, style="CardMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 18))

        ttk.Label(panel, text="Cantidad", style="Field.TLabel").grid(row=3, column=0, sticky="w")
        self.qty_var = tk.StringVar(value="1")
        QuantityStepper(panel, self.qty_var).grid(row=4, column=0, sticky="ew", pady=(4, 14))

        ttk.Label(panel, text="Vender por", style="Field.TLabel").grid(row=5, column=0, sticky="w")
        self.unit_type_var = tk.StringVar()
        self.unit_combo = ttk.Combobox(panel, textvariable=self.unit_type_var, state="readonly")
        self.unit_combo.grid(row=6, column=0, sticky="ew", pady=(4, 14))
        self.unit_type_var.trace_add("write", lambda *_: self._update_total())

        ttk.Label(panel, text="Fecha (AAAA-MM-DD)", style="Field.TLabel").grid(row=7, column=0, sticky="w")
        self.date_var = tk.StringVar(value=today_str())
        ttk.Entry(panel, textvariable=self.date_var).grid(row=8, column=0, sticky="ew", pady=(4, 18))

        ttk.Frame(panel, style="Rule.TFrame", height=1).grid(row=9, column=0, sticky="ew")
        total_row = ttk.Frame(panel, style="CardInner.TFrame")
        total_row.grid(row=10, column=0, sticky="ew", pady=(12, 16))
        ttk.Label(total_row, text="Total", style="CardMuted.TLabel").pack(side="left")
        self.total_var = tk.StringVar(value="S/ 0.00")
        ttk.Label(total_row, textvariable=self.total_var, style="Card.TLabel", font=ui_font(20, "bold")).pack(side="right")

        self.btn_register = Button(panel, text="Registrar salida", variant="primary", state="disabled",
                                   command=self._register_sale)
        self.btn_register.grid(row=11, column=0, sticky="ew")

        self.qty_var.trace_add("write", lambda *_: self._update_total())

    # -- tabla ------------------------------------------------------------------
    def _debounced_search(self) -> None:
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self._refresh_table_internal)

    def refresh_table(self) -> None:
        self._debounced_search()

    def _refresh_table_internal(self) -> None:
        self._search_job = None
        self.tree.delete(*self.tree.get_children())
        for p in self.repo.search_products(self.search_var.get()):
            self.tree.insert("", "end", iid=p["id"], values=(
                p["commercial_name"], format_stock_display(p), price_summary(p)))
        stripe_tree(self.tree, empty_text="Ningún producto coincide con la búsqueda")
        if self.selected_product_id and self.tree.exists(self.selected_product_id):
            self.tree.selection_set(self.selected_product_id)
            self._show_stock(self.repo.get_product(self.selected_product_id))
        elif self.selected_product_id and not self.repo.get_product(self.selected_product_id):
            self._clear_selection()

    # -- panel ------------------------------------------------------------------
    def _clear_selection(self) -> None:
        self.selected_product_id = None
        self.selected_name_var.set("Selecciona un producto")
        self.stock_display_var.set("")
        self.unit_combo.configure(values=[])
        self.unit_type_var.set("")
        self.btn_register.configure(state="disabled")
        self._update_total()

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        product = self.repo.get_product(selection[0])
        if not product:
            return
        self.selected_product_id = product["id"]
        self.selected_name_var.set(product["commercial_name"])
        self._show_stock(product)
        # Texto del combo: "Blister · S/ 3.50"; el dict recuerda a qué nivel corresponde cada texto
        self._unit_types = {f"{label} · S/ {resolve_price(product, level):.2f}": level
                            for label, level in unit_choices(product, for_sale=True).items()}
        self.unit_combo.configure(values=list(self._unit_types))
        self.unit_type_var.set(next(reversed(self._unit_types)) if self.unit_type_var.get() not in self._unit_types
                               else self.unit_type_var.get())
        self.btn_register.configure(state="normal")
        self._update_total()

    def _show_stock(self, product: Dict) -> None:
        self.stock_display_var.set(f"Existencias: {format_stock_display(product)}")

    def _update_total(self) -> None:
        product = self.repo.get_product(self.selected_product_id) if self.selected_product_id else None
        try:
            qty = int(self.qty_var.get())
        except ValueError:
            qty = 0
        level = self._unit_types.get(self.unit_type_var.get())
        ok = product and qty > 0 and level
        self.total_var.set(f"S/ {money(qty * resolve_price(product, level)):.2f}" if ok else "S/ 0.00")

    # -- registro ---------------------------------------------------------------
    def _register_sale(self) -> None:
        product = self.repo.get_product(self.selected_product_id) if self.selected_product_id else None
        if not product:
            messagebox.showwarning("Atención", "Selecciona un producto de la tabla.")
            return
        try:
            qty = int(self.qty_var.get())
            if qty <= 0:
                raise ValueError()
            parse_date(self.date_var.get())
        except ValueError:
            messagebox.showerror("Datos inválidos", "La cantidad debe ser un entero positivo y la fecha AAAA-MM-DD.")
            return

        unit_type = self._unit_types.get(self.unit_type_var.get())
        if not unit_type:
            messagebox.showwarning("Atención", "Elige la unidad en que se vende.")
            return
        needed = convert_units_to_base(qty, unit_type, product.get("unit_hierarchy", {}))
        if product["stock"] < needed:
            messagebox.showerror("Stock insuficiente", f"Se necesitan {needed} unidades base y solo hay "
                                 f"{product['stock']}.\nExistencias: {format_stock_display(product)}")
            return

        unit_display = format_quantity(product, unit_type, qty)
        movement = {
            "id": str(uuid4()),
            "product_id": product["id"],
            "product_name": product["commercial_name"],
            "type": "Salida",
            "quantity": qty,
            "unit_type": unit_type,
            "date": self.date_var.get(),
            "notes": f"Venta directa - {unit_display}",
            "recorded_at": datetime.now().isoformat(),
            "username": self.app.current_user_type if self.app else "admin",
            "user_display_name": self.app.current_user_name if self.app else "Admin",
        }
        try:
            self.repo.record_movement(movement)  # fija precio/costo, ajusta stock
            if self.app and self.app.current_user_type != "admin":
                self.repo.log_activity(
                    username=self.app.current_user_type, user_name=self.app.current_user_name,
                    action="Registro de Salida",
                    details={"product_name": product["commercial_name"], "quantity": unit_display,
                             "movement_type": "Salida", "total": movement["line_total"],
                             "date": self.date_var.get()})
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        total = movement["line_total"]
        self.qty_var.set("1")
        self.refresh_callback()
        messagebox.showinfo("Venta registrada", f"{unit_display} de {product['commercial_name']}\nTotal: S/ {total:.2f}")
