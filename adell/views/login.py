import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional


ROLE_LABELS = {"superadmin": "Super administrador", "admin": "Administrador", "personal": "Personal"}
ROLE_ORDER = {"superadmin": 0, "admin": 1, "personal": 2}
from adell.store import DataStore
from adell.ui.theme import THEME, display_font, ui_font
from adell.ui.widgets import Button, draw_logo


class LoginDialog:
    """Pantalla de acceso. Tras cerrarse, `result` indica si el acceso fue válido y
    `user_type` (usuario), `user_name` y `user_role` describen la sesión."""

    WIDTH, HEIGHT = 800, 500

    def __init__(self, parent: tk.Tk, repo: DataStore) -> None:
        self.parent = parent
        self.repo = repo
        self.result = False
        self.user_type: Optional[str] = None
        self.user_name: Optional[str] = None
        self.user_role: Optional[str] = None

        self.top = tk.Toplevel(parent)
        self.top.title("Farmacia · Acceso")
        self.top.configure(bg=THEME["bg"])
        self.top.resizable(False, False)
        x = (self.top.winfo_screenwidth() - self.WIDTH) // 2
        y = (self.top.winfo_screenheight() - self.HEIGHT) // 3
        self.top.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        self._build()
        self.top.grab_set()
        parent.wait_window(self.top)

    def _build(self) -> None:
        t = THEME
        # Panel de marca
        brand = tk.Frame(self.top, bg=t["primary"], width=300)
        brand.pack(side="left", fill="y")
        brand.pack_propagate(False)
        draw_logo(brand, 40, t["primary"]).place(x=36, y=40)
        tk.Label(brand, text="Farmacia", font=display_font(28, "bold"), bg=t["primary"], fg="#ffffff",
                 justify="left").place(x=34, y=200)
        tk.Label(brand, text="Inventario, entradas y ventas\nde tu farmacia, en un solo lugar.",
                 font=ui_font(11), bg=t["primary"], fg="#b9d3c8", justify="left").place(x=36, y=252)
        tk.Label(brand, text="Datos guardados en este equipo", font=ui_font(9),
                 bg=t["primary"], fg="#8fb4a5").place(x=36, y=self.HEIGHT - 44)

        # Formulario
        form = tk.Frame(self.top, bg=t["bg"])
        form.pack(side="left", fill="both", expand=True, padx=60)
        tk.Frame(form, bg=t["bg"], height=70).pack()
        tk.Label(form, text="Iniciar sesión", font=display_font(24, "bold"), bg=t["bg"], fg=t["text"]).pack(anchor="w")
        tk.Label(form, text="Elige tu usuario e ingresa tu contraseña.", font=ui_font(10),
                 bg=t["bg"], fg=t["muted"]).pack(anchor="w", pady=(2, 26))

        users = self.repo.get_all_users()
        ordered = sorted(users.items(), key=lambda kv: ROLE_ORDER.get(kv[1].get("role", "personal"), 2))
        self._users_by_label: Dict[str, str] = {
            f"{u['name']}  ·  {ROLE_LABELS.get(u.get('role', 'personal'), 'Personal')}": name for name, u in ordered
        }
        labels = list(self._users_by_label)

        tk.Label(form, text="Usuario", font=ui_font(9), bg=t["bg"], fg=t["muted"]).pack(anchor="w")
        self.user_label_var = tk.StringVar(value=labels[0] if labels else "")
        ttk.Combobox(form, textvariable=self.user_label_var, values=labels, state="readonly").pack(
            fill="x", pady=(4, 16))

        tk.Label(form, text="Contraseña", font=ui_font(9), bg=t["bg"], fg=t["muted"]).pack(anchor="w")
        pw_row = tk.Frame(form, bg=t["bg"])
        pw_row.pack(fill="x", pady=(4, 0))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(pw_row, textvariable=self.password_var, show="•")
        self.password_entry.pack(side="left", fill="x", expand=True)
        toggle = tk.Label(pw_row, text="Mostrar", font=ui_font(9, "bold"), bg=t["bg"], fg=t["primary"],
                          cursor="hand2", padx=10)
        toggle.pack(side="right")

        def toggle_password(_e=None):
            hidden = self.password_entry.cget("show") != ""
            self.password_entry.configure(show="" if hidden else "•")
            toggle.configure(text="Ocultar" if hidden else "Mostrar")
        toggle.bind("<Button-1>", toggle_password)

        Button(form, text="Ingresar", variant="primary", command=self._handle_login).pack(fill="x", pady=(26, 10))
        tk.Label(form, text="Enter para ingresar  ·  Esc para salir", font=ui_font(9),
                 bg=t["bg"], fg=t["faint"]).pack(anchor="w")

        self.top.after(50, self.password_entry.focus_force)
        self.top.bind("<Return>", lambda _e: self._handle_login())
        self.top.bind("<Escape>", lambda _e: self.top.destroy())

    def _handle_login(self) -> None:
        username = self._users_by_label.get(self.user_label_var.get())
        password = self.password_var.get()
        if not password:
            messagebox.showwarning("Falta la contraseña", "Ingresa tu contraseña para continuar.", parent=self.top)
            return
        if not username or not self.repo.verify_password(username, password):
            messagebox.showerror("Acceso denegado", "La contraseña es incorrecta.", parent=self.top)
            self.password_var.set("")
            self.password_entry.focus()
            return

        user = self.repo.get_user(username)
        self.result = True
        self.user_type = username
        self.user_name = user["name"]
        self.user_role = user["role"]
        self.top.destroy()
