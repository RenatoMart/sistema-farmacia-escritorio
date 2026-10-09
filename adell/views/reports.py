from datetime import date, timedelta
from typing import Dict, List
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from adell.domain import movement_amounts, format_quantity, DATE_FMT, parse_date, today_str
from adell.store import DataStore
from adell.ui.widgets import Button, StatStrip, build_tree, page_header, update_empty_state

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


class ReportsView(ttk.Frame):
    def __init__(self, parent, repo: DataStore, app=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.app = app
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        header = page_header(self, "Reportes", "Entradas, ventas y utilidad por rango de fechas.")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        Button(header.actions, text="Descargar PDF", variant="primary", command=self._export_pdf).pack()

        controls = ttk.LabelFrame(self, text="  Filtros  ", padding=16)
        controls.grid(row=1, column=0, sticky="ew")
        for idx in range(4): controls.columnconfigure(idx, weight=1)

        ttk.Label(controls, text="Rango Rápido").grid(row=0, column=0, sticky="w")
        self.range_var = tk.StringVar(value="Esta Semana")
        range_combo = ttk.Combobox(controls, textvariable=self.range_var, values=["Hoy", "Esta Semana", "Este Mes", "Personalizado"], state="readonly")
        range_combo.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        range_combo.bind("<<ComboboxSelected>>", self._on_range_change)

        ttk.Label(controls, text="Fecha Inicio (Año-Mes-Día)").grid(row=0, column=1, sticky="w")
        self.start_var = tk.StringVar(value=(date.today() - timedelta(days=date.today().weekday())).strftime(DATE_FMT))
        start_entry = ttk.Entry(controls, textvariable=self.start_var)
        start_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        start_entry.bind('<FocusOut>', lambda e: self._on_filter_change())
        start_entry.bind('<Return>', lambda e: self._on_filter_change())

        ttk.Label(controls, text="Fecha Fin (Año-Mes-Día)").grid(row=0, column=2, sticky="w")
        self.end_var = tk.StringVar(value=today_str())
        end_entry = ttk.Entry(controls, textvariable=self.end_var)
        end_entry.grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        end_entry.bind('<FocusOut>', lambda e: self._on_filter_change())
        end_entry.bind('<Return>', lambda e: self._on_filter_change())

        ttk.Label(controls, text="Tipo").grid(row=0, column=3, sticky="w")
        self.type_var = tk.StringVar(value="Todos")
        type_combo = ttk.Combobox(controls, textvariable=self.type_var, values=["Todos", "Entrada", "Salida"], state="readonly")
        type_combo.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())

        # Opción para incluir productos eliminados
        self.show_deleted_var = tk.BooleanVar(value=False)
        deleted_check = ttk.Checkbutton(controls, text="Incluir productos eliminados", variable=self.show_deleted_var, command=self._on_filter_change)
        deleted_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Guía de formato
        ttk.Label(controls, text="Formato de fecha: AAAA-MM-DD (ej. 2026-01-10)", style="CardMuted.TLabel").grid(
            row=2, column=2, columnspan=2, sticky="e", pady=(10, 0))

        self.entries_var = tk.StringVar(value="S/ 0.00")
        self.sales_var = tk.StringVar(value="S/ 0.00")
        self.profit_var = tk.StringVar(value="S/ 0.00")

        StatStrip(self, [
            ("Inversión en entradas", self.entries_var, "default"),
            ("Ventas", self.sales_var, "default"),
            ("Utilidad", self.profit_var, "success"),
        ]).grid(row=2, column=0, sticky="ew", pady=16)

        preview = ttk.LabelFrame(self, text="  Movimientos del periodo  ", padding=15)
        preview.grid(row=3, column=0, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)

        # Botón para restablecer columnas
        btn_frame = ttk.Frame(preview)
        btn_frame.grid(row=0, column=0, sticky="e", pady=(0, 5))
        Button(btn_frame, text="Restablecer columnas", variant="secondary", command=lambda: self._reset_reports_columns()).pack(side="right")

        tree_box, self.tree = build_tree(preview, ("date", "product", "type", "qty", "total", "gain"), height=10)

        # Anchos por defecto
        self.default_reports_widths = {
            "date": 120,
            "product": 250,
            "type": 100,
            "qty": 130,
            "total": 110,
            "gain": 110
        }

        headers = {"date": "Fecha", "product": "Producto", "type": "Tipo", "qty": "Cantidad", "total": "Total",
                   "gain": "Utilidad"}
        for key, label in headers.items():
            anchor = {"product": "w", "total": "e", "gain": "e"}.get(key, "center")
            self.tree.heading(key, text=label, anchor=anchor)
            self.tree.column(key, width=self.default_reports_widths[key], minwidth=80, stretch=True, anchor=anchor)
        tree_box.grid(row=1, column=0, sticky="nsew")

        self._apply_filters()

    def _on_range_change(self, _event) -> None:
        r = self.range_var.get()
        today = date.today()
        if r == "Hoy":
            self.start_var.set(today_str())
            self.end_var.set(today_str())
        elif r == "Esta Semana":
            start = today - timedelta(days=today.weekday())
            self.start_var.set(start.strftime(DATE_FMT))
            self.end_var.set(today_str())
        elif r == "Este Mes":
            start = today.replace(day=1)
            self.start_var.set(start.strftime(DATE_FMT))
            self.end_var.set(today_str())
        # Aplicar filtros automáticamente
        self._apply_filters()

    def _on_filter_change(self) -> None:
        """Actualizar reportes automáticamente cuando cambian los filtros."""
        self._apply_filters()

    def _apply_filters(self) -> None:
        try:
            start = parse_date(self.start_var.get()) if self.start_var.get() else None
            end = parse_date(self.end_var.get()) if self.end_var.get() else None
        except ValueError:
            messagebox.showerror("Error", "Fechas inválidas")
            return

        # Determinar si filtrar por usuario
        username_filter = None
        if self.app and self.app.current_user_type != "admin":
            username_filter = self.app.current_user_type

        movements = self.repo.get_movements(self.type_var.get(), start, end, username=username_filter)
        for row in self.tree.get_children(): self.tree.delete(row)
        self.current_rows = []  # filas ya formateadas, las usa la exportación a PDF

        total_inv = 0.0
        total_sales = 0.0
        profit = 0.0

        # Obtener lista de productos existentes para filtrar si es necesario
        show_deleted = self.show_deleted_var.get()
        existing_products = {p["id"] for p in self.repo.products} if not show_deleted else None

        for m in sorted(movements, key=lambda x: x["date"], reverse=True):
            # Verificar si el producto aún existe (solo si no se quieren mostrar eliminados)
            if not show_deleted and existing_products and m["product_id"] not in existing_products:
                continue  # Omitir movimientos de productos eliminados

            total, _cost, m_gain = movement_amounts(m)
            if m["type"] == "Entrada":
                total_inv += total
            else:
                total_sales += total
                profit += m_gain

            # Obtener nombre del producto, indicar si está eliminado
            product = self.repo.get_product(m["product_id"])
            if product:
                p_name = m.get("product_name") or product.get("commercial_name", "Desconocido")
                quantity = format_quantity(product, m.get("unit_type", "base_unit"), m["quantity"])
            else:
                p_name = m.get("product_name", "Producto Eliminado")
                quantity = str(m["quantity"])
                if show_deleted:
                    p_name += " (ELIMINADO)"

            row = (m["date"], p_name, m["type"], quantity, f"S/ {total:.2f}",
                   f"S/ {m_gain:.2f}" if m["type"] == "Salida" else "—")
            self.tree.insert("", "end", values=row, tags=("entry" if m["type"] == "Entrada" else "exit",))
            self.current_rows.append(list(row))

        update_empty_state(self.tree, "No hay movimientos en este periodo")
        self.entries_var.set(f"S/ {total_inv:.2f}")
        self.sales_var.set(f"S/ {total_sales:.2f}")
        self.profit_var.set(f"S/ {profit:.2f}")

    def _export_pdf(self) -> None:
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Error", "Instale reportlab")
            return
        if not getattr(self, "current_rows", None): return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path: return
        ReportExporter.export(path, self.current_rows, {
            "entries": f"Inversión: {self.entries_var.get()}",
            "sales": f"Ventas: {self.sales_var.get()}",
            "profit": f"Utilidad: {self.profit_var.get()}",
        }, (self.start_var.get(), self.end_var.get()))
        messagebox.showinfo("Éxito", "Reporte PDF generado")

    def _reset_reports_columns(self) -> None:
        """Restablecer el ancho de las columnas de reportes a sus valores por defecto"""
        for key, width in self.default_reports_widths.items():
            self.tree.column(key, width=width)


class ReportExporter:
    @staticmethod
    def export(path: str, rows: List[List[str]], summary: Dict[str, str], date_range) -> None:
        doc = SimpleDocTemplate(path, pagesize=LETTER)
        styles = getSampleStyleSheet()
        content = [
            Paragraph("Reporte de movimientos", styles["Title"]),
            Paragraph(f"Rango: {date_range[0]} a {date_range[1]}", styles["Normal"]),
            Spacer(1, 12),
            Paragraph(summary["entries"], styles["Normal"]),
            Paragraph(summary["sales"], styles["Normal"]),
            Paragraph(summary["profit"], styles["Normal"]),
            Spacer(1, 12),
        ]
        table_data = [["Fecha", "Producto", "Tipo", "Cantidad", "Total", "Utilidad"]] + rows
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d5c4a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dcd7ca")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f6f0")]),
                ]
            )
        )
        content.append(table)
        doc.build(content)
