from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
from adell.domain import DATE_FMT, parse_date
from adell.store import DataStore
from adell.ui.widgets import Button, build_tree, page_header, stripe_tree


class ActivityMonitorView(ttk.Frame):
    """Vista para que el administrador monitoree las actividades del personal"""
    def __init__(self, parent: ttk.Frame, repo: DataStore) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.repo = repo

        # Variables para los filtros
        self.user_var = tk.StringVar(value="Todos")
        self.period_var = tk.StringVar(value="Hoy")
        self.start_var = tk.StringVar(value="")
        self.end_var = tk.StringVar(value="")

        # Establecer fechas por defecto para "Hoy"
        self._set_date_range_for_period("Hoy")

        self._build()


    def _build(self) -> None:
        # Título
        header = page_header(self, "Monitor de actividades", "Qué registró cada miembro del personal.")
        header.pack(fill="x", pady=(0, 16))
        Button(header.actions, text="Actualizar", command=self._refresh_data).pack()

        # Filtros
        filters_frame = ttk.LabelFrame(self, text="  Filtros  ", padding=15)
        filters_frame.pack(fill="x", pady=(0, 15))

        # Primera fila de filtros
        # Usuario
        ttk.Label(filters_frame, text="Usuario:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        user_combo = ttk.Combobox(filters_frame, textvariable=self.user_var, state="readonly", width=15)
        self._users_by_label = {f"{u['name']} ({username})": username for username, u in self.repo.get_all_users().items()}
        user_combo["values"] = ["Todos"] + list(self._users_by_label)
        user_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        user_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_data())

        # Periodo rápido
        ttk.Label(filters_frame, text="Periodo:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        period_combo = ttk.Combobox(filters_frame, textvariable=self.period_var, state="readonly", width=15)
        period_combo["values"] = ["Hoy", "Esta Semana", "Este Mes", "Personalizado"]
        period_combo.grid(row=0, column=3, sticky="w", padx=(0, 20))
        period_combo.bind("<<ComboboxSelected>>", lambda e: self._on_period_change())

        # Botón de aplicar filtros
        Button(filters_frame, text="Aplicar filtros", variant="primary", command=self._refresh_data).grid(row=0, column=4, padx=10)

        # Segunda fila - Fechas personalizadas (solo visible cuando se selecciona "Personalizado")
        self.custom_dates_frame = ttk.Frame(filters_frame)
        self.custom_dates_frame.grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))

        ttk.Label(self.custom_dates_frame, text="Desde (YYYY-MM-DD):").pack(side="left", padx=(0, 10))
        self.start_entry = ttk.Entry(self.custom_dates_frame, textvariable=self.start_var, width=15)
        self.start_entry.pack(side="left", padx=(0, 20))

        ttk.Label(self.custom_dates_frame, text="Hasta (YYYY-MM-DD):").pack(side="left", padx=(0, 10))
        self.end_entry = ttk.Entry(self.custom_dates_frame, textvariable=self.end_var, width=15)
        self.end_entry.pack(side="left", padx=(0, 20))

        # Ocultar campos de fechas personalizadas por defecto
        self._toggle_custom_dates()

        # Tabla de actividades
        columns = ("fecha_hora", "usuario", "accion", "producto", "cantidad", "tipo_movimiento", "detalles")
        table_frame, self.tree = build_tree(self, columns, height=12)
        table_frame.pack(fill="both", expand=True)

        # Configurar columnas
        self.tree.heading("fecha_hora", text="Fecha y Hora", anchor="center")
        self.tree.heading("usuario", text="Usuario", anchor="center")
        self.tree.heading("accion", text="Acción", anchor="center")
        self.tree.heading("producto", text="Producto", anchor="w")
        self.tree.heading("cantidad", text="Cantidad", anchor="center")
        self.tree.heading("tipo_movimiento", text="Tipo", anchor="center")
        self.tree.heading("detalles", text="Detalles", anchor="w")

        self.tree.column("fecha_hora", width=150, minwidth=120, stretch=True, anchor="center")
        self.tree.column("usuario", width=100, minwidth=80, stretch=True, anchor="center")
        self.tree.column("accion", width=120, minwidth=100, stretch=True, anchor="center")
        self.tree.column("producto", width=200, minwidth=150, stretch=True, anchor="w")
        self.tree.column("cantidad", width=80, minwidth=60, stretch=True, anchor="center")
        self.tree.column("tipo_movimiento", width=100, minwidth=80, stretch=True, anchor="center")
        self.tree.column("detalles", width=250, minwidth=150, stretch=True, anchor="w")

        # Resumen al final
        summary_frame = ttk.Frame(self, style="Main.TFrame")
        summary_frame.pack(fill="x", pady=(12, 0))

        self.total_var = tk.StringVar(value="Total de actividades: 0")
        ttk.Label(summary_frame, textvariable=self.total_var, style="Muted.TLabel").pack(side="left")

        # Cargar datos iniciales
        self._refresh_data()

    def _set_date_range_for_period(self, period: str) -> None:
        """Configura el rango de fechas según el periodo seleccionado"""
        today = date.today()

        if period == "Hoy":
            self.start_var.set(today.strftime(DATE_FMT))
            self.end_var.set(today.strftime(DATE_FMT))
        elif period == "Esta Semana":
            # Calcular el inicio de la semana (lunes)
            start_of_week = today - timedelta(days=today.weekday())
            self.start_var.set(start_of_week.strftime(DATE_FMT))
            self.end_var.set(today.strftime(DATE_FMT))
        elif period == "Este Mes":
            # Primer día del mes actual
            start_of_month = today.replace(day=1)
            self.start_var.set(start_of_month.strftime(DATE_FMT))
            self.end_var.set(today.strftime(DATE_FMT))
        # Si es "Personalizado", no modificamos las fechas

    def _on_period_change(self) -> None:
        """Maneja el cambio de periodo"""
        period = self.period_var.get()

        if period != "Personalizado":
            self._set_date_range_for_period(period)
            self._refresh_data()

        # Mostrar/ocultar campos de fechas personalizadas
        self._toggle_custom_dates()

    def _toggle_custom_dates(self) -> None:
        """Muestra u oculta los campos de fechas personalizadas"""
        if self.period_var.get() == "Personalizado":
            self.custom_dates_frame.grid()
            self.start_entry.config(state="normal")
            self.end_entry.config(state="normal")
        else:
            self.custom_dates_frame.grid_remove()

    def _refresh_data(self) -> None:
        """Actualiza los datos de actividades"""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Obtener filtros
        username = None
        user_selection = self.user_var.get()
        if user_selection != "Todos":
            username = self._users_by_label.get(user_selection)

        start_date = None
        end_date = None

        try:
            if self.start_var.get():
                start_date = parse_date(self.start_var.get())
            if self.end_var.get():
                end_date = parse_date(self.end_var.get())
        except ValueError:
            messagebox.showerror("Error", "Formato de fecha inválido. Use YYYY-MM-DD")
            return

        # Obtener actividades filtradas
        activities = self.repo.get_activities(username=username, start_date=start_date, end_date=end_date)

        # Llenar tabla
        for activity in activities:
            fecha_hora = activity.get("timestamp", "")
            usuario = activity.get("user_name", "")
            accion = activity.get("action", "")
            details = activity.get("details", {})

            producto = details.get("product_name", "-")
            cantidad = details.get("quantity", "-")
            tipo_movimiento = details.get("movement_type", "-")

            # Construir detalles adicionales
            if "total" in details:
                detalles_text = f"Total: S/ {details['total']:.2f}"
            elif accion == "Registro de Entrada":  # registros anteriores al modelo de precios por unidad
                detalles_text = f"Precio Adq.: S/ {details.get('acquisition_price', 0):.2f}"
            elif accion == "Registro de Salida":
                detalles_text = f"Precio Venta: S/ {details.get('sale_price', 0):.2f}"
            else:
                detalles_text = ""

            self.tree.insert("", "end", values=(
                fecha_hora,
                usuario,
                accion,
                producto,
                cantidad,
                tipo_movimiento,
                detalles_text
            ))

        stripe_tree(self.tree, empty_text="No hay actividades en este periodo")

        # Actualizar total
        self.total_var.set(f"Total de actividades: {len(activities)}")
