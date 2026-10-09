"""Ventana principal, arranque de la aplicación y elección de la carpeta de datos."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

from adell.store import DataStore, PathConfig
from adell.ui.theme import THEME, configure_style, display_font, ui_font
from adell.ui.widgets import NavButton, apply_card_styles, draw_logo, nav_group_label
from adell.views.activity import ActivityMonitorView
from adell.views.entries import EntriesView
from adell.views.inventory import InventoryView
from adell.views.login import LoginDialog
from adell.views.reports import ReportsView
from adell.views.sales import SalesView
from adell.views.users import UserManagementView

ROLE_LABELS = {"superadmin": "Super administrador", "admin": "Administrador", "personal": "Personal"}

# Secciones del menú lateral: (título del grupo, [vistas]). Las vistas que no existan
# para el rol actual (p. ej. el monitor para personal) se omiten.
NAV_GROUPS = (
    ("Operación", ("Inventario", "Entradas", "Salidas")),
    ("Análisis", ("Reportes",)),
    ("Administración", ("Personal", "Monitor de Actividades")),
)


def ask_data_path_first_time() -> Optional[Path]:
    """Pregunta al usuario dónde guardar los datos (primera vez)."""
    root = tk.Tk()
    root.withdraw()

    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - 250
    y = (root.winfo_screenheight() // 2) - 150
    root.geometry(f'+{x}+{y}')

    msg = (
        "¡Bienvenido a Farmacia!\n\n"
        "Es la primera vez que ejecutas el programa.\n\n"
        "Necesitas configurar dónde se guardarán los datos\n"
        "de la farmacia (productos, movimientos, reportes, etc.).\n\n"
        "Haz clic en OK para continuar..."
    )

    messagebox.showinfo("Configuración Inicial", msg, parent=root)

    response = messagebox.askyesno(
        "Configuración de Datos",
        "¿Deseas CREAR una nueva carpeta para los datos?\n\n"
        "• SÍ: Se creará una carpeta 'DatosFarmacia' donde elijas\n"
        "• NO: Selecciona una carpeta existente con datos previos",
        parent=root
    )

    if response:  # Crear nueva
        selected_dir = filedialog.askdirectory(
            parent=root,
            title="Selecciona dónde crear la carpeta 'DatosFarmacia'",
            mustexist=True
        )

        if selected_dir:
            data_path = Path(selected_dir) / "DatosFarmacia"
            try:
                data_path.mkdir(parents=True, exist_ok=True)
                messagebox.showinfo(
                    "Carpeta Creada",
                    f"✓ Carpeta creada exitosamente:\n\n{data_path}\n\n"
                    "Los archivos de la farmacia se guardarán aquí.",
                    parent=root
                )
                root.destroy()
                return data_path
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo crear la carpeta:\n{e}", parent=root)
                root.destroy()
                return None
    else:  # Seleccionar existente
        selected_dir = filedialog.askdirectory(
            parent=root,
            title="Selecciona la carpeta con los datos existentes",
            mustexist=True
        )

        if selected_dir:
            data_path = Path(selected_dir)
            has_json = any(data_path.glob("*.json"))

            if not has_json:
                response = messagebox.askyesno(
                    "Carpeta Vacía",
                    "La carpeta seleccionada no contiene archivos de datos.\n\n"
                    "¿Deseas usarla de todas formas?\n"
                    "Se crearán nuevos archivos aquí.",
                    parent=root
                )
                if not response:
                    root.destroy()
                    return None

            messagebox.showinfo("Carpeta Seleccionada", f"✓ Los datos se guardarán en:\n\n{data_path}", parent=root)
            root.destroy()
            return data_path

    root.destroy()
    return None


class PharmacyApp(tk.Tk):
    """Ventana principal: pide acceso, arma el menú lateral y muestra una vista a la vez."""

    def __init__(self, data_path: Path) -> None:
        super().__init__()
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  # nítido en pantallas HiDPI de Windows
        except Exception:
            pass

        self.title("Farmacia")
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width, height = int(screen_w * 0.8), int(screen_h * 0.85)
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 3}")
        self.minsize(int(screen_w * 0.5), int(screen_h * 0.5))

        self.data_path = data_path
        self.repo = DataStore(data_path)
        configure_style(self)
        self.withdraw()
        if not self._login():
            self.destroy()
            return
        self.deiconify()
        self._build_layout()

    # -- sesión ---------------------------------------------------------------
    def _login(self) -> bool:
        """Muestra el login; guarda usuario/rol/permisos de la sesión. False si cancela."""
        login = LoginDialog(self, self.repo)
        if not login.result:
            return False
        self.current_user_type = login.user_type
        self.current_user_name = login.user_name
        self.current_user_role = login.user_role
        self.current_user_permissions = self.repo.get_user(login.user_type)["permissions"]
        return True

    def _logout(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self.withdraw()
        if not self._login():
            self.destroy()
            return
        self.deiconify()
        self._build_layout()

    def has_permission(self, permission: str) -> bool:
        return "all" in self.current_user_permissions or permission in self.current_user_permissions

    # -- layout ---------------------------------------------------------------
    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.content = tk.Frame(self, bg=THEME["bg"])
        self.content.grid(row=0, column=1, sticky="nsew", padx=36, pady=(26, 20))
        self._build_views()
        self._build_sidebar()
        self.show_view("Inventario")

    def _build_views(self) -> None:
        refresh = self._refresh_all
        self.inventory_view = InventoryView(self.content, self.repo, refresh, self)
        self.entries_view = EntriesView(self.content, self.repo, refresh, self)
        self.sales_view = SalesView(self.content, self.repo, refresh, self)
        self.reports_view = ReportsView(self.content, self.repo, app=self)
        self.views = {
            "Inventario": self.inventory_view,
            "Entradas": self.entries_view,
            "Salidas": self.sales_view,
            "Reportes": self.reports_view,
            "Personal": UserManagementView(self.content, self.repo, self.current_user_role, self.current_user_type),
        }
        if self.current_user_role in ("admin", "superadmin"):
            self.views["Monitor de Actividades"] = ActivityMonitorView(self.content, self.repo)
        apply_card_styles(self.content)

    def _build_sidebar(self) -> None:
        t = THEME
        nav = tk.Frame(self, bg=t["sidebar"], width=236)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.pack_propagate(False)
        tk.Frame(self, bg=t["border"], width=1).grid(row=0, column=0, sticky="nse")

        brand = tk.Frame(nav, bg=t["sidebar"])
        brand.pack(fill="x", padx=22, pady=(28, 30))
        draw_logo(brand, 30, t["sidebar"]).pack(side="left")
        names = tk.Frame(brand, bg=t["sidebar"])
        names.pack(side="left", padx=(11, 0))
        tk.Label(names, text="Farmacia", font=display_font(16, "bold"), bg=t["sidebar"], fg=t["text"]).pack(anchor="w")
        tk.Label(names, text="Inventario y ventas", font=ui_font(9), bg=t["sidebar"], fg=t["muted"]).pack(anchor="w")

        # Zona inferior primero, para que siempre quede visible
        bottom = tk.Frame(nav, bg=t["sidebar"])
        bottom.pack(side="bottom", fill="x", pady=(0, 14))
        NavButton(bottom, "Cerrar sesión", self._logout).pack(fill="x")
        tk.Frame(bottom, bg=t["border"], height=1).pack(fill="x", padx=22, pady=(0, 14))
        who = tk.Frame(bottom, bg=t["sidebar"])
        who.pack(fill="x", padx=22, pady=(0, 8))
        tk.Label(who, text=self.current_user_name, font=ui_font(10, "bold"), bg=t["sidebar"], fg=t["text"]).pack(anchor="w")
        tk.Label(who, text=ROLE_LABELS.get(self.current_user_role, "Personal"), font=ui_font(9),
                 bg=t["sidebar"], fg=t["muted"]).pack(anchor="w")

        self.nav_buttons = {}
        for group, names_in_group in NAV_GROUPS:
            available = [n for n in names_in_group if n in self.views]
            if not available:
                continue
            nav_group_label(nav, group).pack(fill="x", padx=22, pady=(0, 4))
            for name in available:
                btn = NavButton(nav, name, lambda n=name: self.show_view(n))
                btn.pack(fill="x")
                self.nav_buttons[name] = btn
            tk.Frame(nav, bg=t["sidebar"], height=16).pack()

    def show_view(self, name: str) -> None:
        for view in self.views.values():
            view.pack_forget()
        self.views[name].pack(fill="both", expand=True)
        for key, btn in self.nav_buttons.items():
            btn.set_active(key == name)

    def _refresh_all(self) -> None:
        """Llamado tras cualquier cambio de datos para que todas las vistas queden al día."""
        self.inventory_view.refresh()
        self.entries_view.refresh_data()
        self.sales_view.refresh_table()
        self.reports_view._apply_filters()


def main() -> None:
    """Configura la carpeta de datos (la primera vez) e inicia la aplicación."""
    path_config = PathConfig()
    if not path_config.has_config():
        data_path = ask_data_path_first_time()
        if not data_path:
            return
        if not path_config.set_data_path(data_path):
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error", "No se pudo guardar la configuración.\nEl programa no puede continuar.")
            return

    data_path = path_config.get_data_path()
    if not data_path:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error", "No se pudo obtener la ruta de datos.\nPor favor, reinicia el programa.")
        return
    PharmacyApp(data_path).mainloop()
