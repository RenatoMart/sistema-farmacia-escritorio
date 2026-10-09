import tkinter as tk
from tkinter import ttk, messagebox
from adell.store import DataStore
from adell.ui.theme import ui_font
from adell.ui.widgets import Button, build_tree, page_header, stripe_tree


class UserManagementView(ttk.Frame):
    """Vista para gestión de personal (crear usuarios, cambiar contraseñas)"""
    def __init__(self, parent: ttk.Frame, repo: DataStore, current_user_role: str, current_username: str) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.repo = repo
        self.current_user_role = current_user_role
        self.current_username = current_username
        self._build()

    def _build(self) -> None:
        # Título
        header = page_header(self, "Personal", "Cuentas de acceso y contraseñas.")
        header.pack(fill="x", pady=(0, 16))
        if self.current_user_role in ["admin", "superadmin"]:
            Button(header.actions, text="Crear usuario", variant="primary", command=self._create_user).pack(side="right")
        Button(header.actions, text="Actualizar", command=self._refresh_data).pack(side="right", padx=(0, 8))

        # Tabla de usuarios
        columns = ("username", "name", "role")
        table_frame, self.tree = build_tree(self, columns, height=10)
        self.tree.configure(selectmode="browse")
        table_frame.pack(fill="both", expand=True, pady=(0, 10))

        # Configurar columnas
        self.tree.heading("username", text="Usuario", anchor="center")
        self.tree.heading("name", text="Nombre", anchor="w")
        self.tree.heading("role", text="Rol", anchor="center")

        self.tree.column("username", width=200, minwidth=150, stretch=True, anchor="center")
        self.tree.column("name", width=300, minwidth=200, stretch=True, anchor="w")
        self.tree.column("role", width=200, minwidth=150, stretch=True, anchor="center")

        # Bind para selección
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)

        # Frame para botones de acción
        action_frame = ttk.Frame(self, style="Main.TFrame")
        action_frame.pack(fill="x", pady=10)

        ttk.Label(action_frame, text="Acciones sobre el usuario seleccionado:", style="Muted.TLabel").pack(side="left", padx=(0, 12))

        # Botón de cambiar contraseña
        self.change_password_btn = Button(action_frame, text="Cambiar contraseña", variant="secondary",
                                             command=self._change_password_selected, state="disabled")
        self.change_password_btn.pack(side="left", padx=5)

        # Botón de eliminar usuario (solo para admin y superadmin)
        if self.current_user_role in ["admin", "superadmin"]:
            self.delete_user_btn = Button(action_frame, text="Eliminar usuario", variant="danger",
                                             command=self._delete_user_selected, state="disabled")
            self.delete_user_btn.pack(side="left", padx=5)

        # Cargar datos
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Actualiza la lista de usuarios"""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Obtener usuarios según permisos
        users = self.repo.get_all_users()

        for username, user_data in users.items():
            role = user_data["role"]

            # Filtrar según permisos
            if self.current_user_role == "admin":
                # Admin solo ve su cuenta y personal
                if role not in ["admin", "personal"]:
                    continue
                if role == "admin" and username != self.current_username:
                    continue
            elif self.current_user_role == "personal":
                # Personal solo ve su propia cuenta
                if username != self.current_username:
                    continue

            role_display = "Super Admin" if role == "superadmin" else \
                          "Administrador" if role == "admin" else "Personal"

            self.tree.insert("", "end", values=(
                username,
                user_data["name"],
                role_display
            ))
        stripe_tree(self.tree)

        # Deshabilitar botones si no hay selección
        self._on_selection_change()

    def _on_selection_change(self, event=None) -> None:
        """Actualiza el estado de los botones según la selección"""
        selection = self.tree.selection()

        if not selection:
            # Sin selección, deshabilitar botones
            self.change_password_btn.config(state="disabled")
            if hasattr(self, 'delete_user_btn'):
                self.delete_user_btn.config(state="disabled")
            return

        # Obtener el usuario seleccionado
        item = self.tree.item(selection[0])
        username = item["values"][0]

        # Habilitar/deshabilitar botón de cambiar contraseña
        if self.repo.can_change_password(self.current_user_role, username) or username == self.current_username:
            self.change_password_btn.config(state="normal")
        else:
            self.change_password_btn.config(state="disabled")

        # Habilitar/deshabilitar botón de eliminar
        if hasattr(self, 'delete_user_btn'):
            if self.current_user_role in ["admin", "superadmin"] and username not in ["superadmin", "admin"]:
                self.delete_user_btn.config(state="normal")
            else:
                self.delete_user_btn.config(state="disabled")

    def _change_password_selected(self) -> None:
        """Cambia la contraseña del usuario seleccionado"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Seleccione un usuario de la lista")
            return

        item = self.tree.item(selection[0])
        username = item["values"][0]
        self._change_password(username)

    def _delete_user_selected(self) -> None:
        """Elimina el usuario seleccionado"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Seleccione un usuario de la lista")
            return

        item = self.tree.item(selection[0])
        username = item["values"][0]
        self._delete_user(username)

    def _create_user(self) -> None:
        """Abre diálogo para crear nuevo usuario"""
        dialog = tk.Toplevel(self)
        dialog.title("Crear Nuevo Usuario")
        dialog.geometry("450x320")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())  # Hacer que el diálogo sea hijo de la ventana principal

        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="Crear Nuevo Usuario", font=ui_font(14, "bold")).pack(pady=20)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill="both", expand=True, padx=30, pady=10)

        ttk.Label(form_frame, text="Nombre Completo:").grid(row=0, column=0, sticky="w", pady=10)
        name_entry = ttk.Entry(form_frame, width=30)
        name_entry.grid(row=0, column=1, pady=10)

        ttk.Label(form_frame, text="Usuario (login):").grid(row=1, column=0, sticky="w", pady=10)
        username_entry = ttk.Entry(form_frame, width=30)
        username_entry.grid(row=1, column=1, pady=10)

        ttk.Label(form_frame, text="Contraseña:").grid(row=2, column=0, sticky="w", pady=10)
        password_entry = ttk.Entry(form_frame, show="*", width=30)
        password_entry.grid(row=2, column=1, pady=10)

        def save_user(event=None):
            name = name_entry.get().strip()
            username = username_entry.get().strip().lower()
            password = password_entry.get()

            if not name or not username or not password:
                messagebox.showerror("Error", "Todos los campos son obligatorios", parent=dialog)
                return

            # Verificar que el usuario no exista
            if self.repo.get_user(username):
                messagebox.showerror("Error", "El usuario ya existe", parent=dialog)
                return

            # Crear usuario
            try:
                self.repo.add_user(username, name, password, role="personal")
                messagebox.showinfo("Éxito", f"Usuario '{name}' creado exitosamente", parent=dialog)
                dialog.destroy()
                self._refresh_data()
            except Exception as e:
                messagebox.showerror("Error", f"Error al crear usuario: {str(e)}", parent=dialog)

        def cancel(event=None):
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)

        Button(button_frame, text="Crear", variant="primary", command=save_user).pack(side="left", padx=5)
        Button(button_frame, text="Cancelar", command=cancel).pack(side="left", padx=5)

        # Bindings de teclado
        dialog.bind("<Return>", save_user)
        dialog.bind("<Escape>", cancel)

        # Establecer foco inicial y hacer modal al final
        name_entry.focus_set()
        dialog.grab_set()
        dialog.wait_window()

    def _change_password(self, username: str) -> None:
        """Abre diálogo para cambiar contraseña"""
        user_data = self.repo.get_user(username)
        if not user_data:
            return

        dialog = tk.Toplevel(self)
        dialog.title("Cambiar Contraseña")
        dialog.geometry("450x350")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())  # Hacer que el diálogo sea hijo de la ventana principal

        # Centrar ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # Determinar si es el mismo usuario cambiando su contraseña
        is_self_change = (username == self.current_username)

        if is_self_change:
            ttk.Label(dialog, text=f"Cambiar Mi Contraseña",
                     font=ui_font(14, "bold")).pack(pady=20)
        else:
            ttk.Label(dialog, text=f"Cambiar Contraseña de {user_data['name']}",
                     font=ui_font(14, "bold")).pack(pady=20)

        form_frame = ttk.Frame(dialog)
        form_frame.pack(fill="both", expand=True, padx=30, pady=10)

        row = 0

        # Solo pedir contraseña actual si el usuario está cambiando SU PROPIA contraseña
        old_password_entry = None
        if is_self_change:
            ttk.Label(form_frame, text="Contraseña Actual:").grid(row=row, column=0, sticky="w", pady=10)
            old_password_entry = ttk.Entry(form_frame, show="*", width=30)
            old_password_entry.grid(row=row, column=1, pady=10)
            old_password_entry.focus()
            row += 1

        ttk.Label(form_frame, text="Nueva Contraseña:").grid(row=row, column=0, sticky="w", pady=10)
        new_password_entry = ttk.Entry(form_frame, show="*", width=30)
        new_password_entry.grid(row=row, column=1, pady=10)
        if not is_self_change:
            new_password_entry.focus()
        row += 1

        ttk.Label(form_frame, text="Confirmar Contraseña:").grid(row=row, column=0, sticky="w", pady=10)
        confirm_password_entry = ttk.Entry(form_frame, show="*", width=30)
        confirm_password_entry.grid(row=row, column=1, pady=10)

        def save_password(event=None):
            # Si se requiere contraseña actual, verificarla
            if old_password_entry:
                old_password = old_password_entry.get()
                if not self.repo.verify_password(username, old_password):
                    messagebox.showerror("Error", "La contraseña actual es incorrecta", parent=dialog)
                    return

            new_password = new_password_entry.get()
            confirm_password = confirm_password_entry.get()

            if not new_password:
                messagebox.showerror("Error", "La contraseña no puede estar vacía", parent=dialog)
                return

            if new_password != confirm_password:
                messagebox.showerror("Error", "Las contraseñas no coinciden", parent=dialog)
                return

            try:
                # Actualizar contraseña
                self.repo.update_user_password(username, new_password)
                messagebox.showinfo("Éxito", "Contraseña actualizada exitosamente", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Error al actualizar contraseña: {str(e)}", parent=dialog)

        def cancel(event=None):
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)

        Button(button_frame, text="Guardar", variant="primary", command=save_password).pack(side="left", padx=5)
        Button(button_frame, text="Cancelar", command=cancel).pack(side="left", padx=5)

        # Bindings de teclado
        dialog.bind("<Return>", save_password)
        dialog.bind("<Escape>", cancel)

        # Hacer modal al final
        dialog.grab_set()
        dialog.wait_window()

    def _delete_user(self, username: str) -> None:
        """Elimina un usuario"""
        user_data = self.repo.get_user(username)
        if not user_data:
            return

        confirm = messagebox.askyesno("Confirmar",
                                     f"¿Está seguro de eliminar al usuario '{user_data['name']}'?\n"
                                     "Esta acción no se puede deshacer.",
                                     parent=self)
        if confirm:
            try:
                self.repo.delete_user(username)
                messagebox.showinfo("Éxito", "Usuario eliminado exitosamente", parent=self)
                self._refresh_data()
            except Exception as e:
                messagebox.showerror("Error", f"Error al eliminar usuario: {str(e)}", parent=self)
