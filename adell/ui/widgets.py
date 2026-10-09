"""Componentes de interfaz reutilizables.

Regla de uso: las vistas no dibujan botones, tablas ni encabezados "a mano";
usan estos componentes para que toda la aplicación comparta el mismo aspecto.
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Sequence, Tuple

from adell.ui.theme import THEME, display_font, ui_font


# ---------------------------------------------------------------------------
# Botón
# ---------------------------------------------------------------------------
class Button(tk.Label):
    """Botón plano con borde fino. `variant`: primary | secondary | danger.

    Acepta `command` y `state` ("normal"/"disabled") como un botón ttk, y se
    puede activar con Enter/Espacio cuando tiene el foco.
    """

    _PALETTES = {
        "primary": ("primary", "#ffffff", "primary_dark", "primary"),
        "secondary": ("surface", "text", "sidebar", "border_strong"),
        "danger": ("surface", "danger", "danger_soft", "#d4aaa0"),
    }

    def __init__(self, parent, text: str = "", command=None, variant: str = "secondary",
                 state: str = "normal", **kw) -> None:
        self._command = command
        self._variant = variant
        self._state = state
        self._hover = False
        options = dict(font=ui_font(10, "bold"), padx=18, pady=8, cursor="hand2", highlightthickness=1,
                       borderwidth=0, takefocus=1, highlightcolor=THEME["primary"])
        options.update(kw)
        super().__init__(parent, text=text, **options)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self._invoke())
        self.bind("<Return>", lambda _e: self._invoke())
        self.bind("<space>", lambda _e: self._invoke())
        self._paint()

    @staticmethod
    def _color(value: str) -> str:
        return THEME.get(value, value)

    def _set_hover(self, hover: bool) -> None:
        self._hover = hover
        self._paint()

    def _invoke(self) -> None:
        if self._state == "normal" and self._command:
            self._command()

    def _paint(self) -> None:
        if self._state == "disabled":
            bg, fg, border, cursor = THEME["row_alt"], THEME["faint"], THEME["border"], "arrow"
        else:
            base, fg, hover, border = (self._color(c) for c in self._PALETTES[self._variant])
            bg, cursor = (hover if self._hover else base), "hand2"
        super().configure(bg=bg, fg=fg, highlightbackground=border, cursor=cursor)

    def configure(self, cnf=None, **kw):
        kw.update(cnf or {})
        self._command = kw.pop("command", self._command)
        self._state = kw.pop("state", self._state)
        self._variant = kw.pop("variant", self._variant)
        result = super().configure(**kw) if kw else None
        self._paint()
        return result

    config = configure

    def cget(self, key):
        return self._state if key == "state" else super().cget(key)


# ---------------------------------------------------------------------------
# Estructura de página
# ---------------------------------------------------------------------------
def page_header(parent, title: str, subtitle: str = "") -> ttk.Frame:
    """Título serif, subtítulo y una línea fina bajo el encabezado.

    Los botones de acción de la página se añaden en `header.actions` (alineados a la derecha).
    """
    frame = ttk.Frame(parent, style="Main.TFrame")
    top = ttk.Frame(frame, style="Main.TFrame")
    top.pack(fill="x")
    titles = ttk.Frame(top, style="Main.TFrame")
    titles.pack(side="left")
    ttk.Label(titles, text=title, style="Header.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(titles, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
    frame.actions = ttk.Frame(top, style="Main.TFrame")
    frame.actions.pack(side="right", anchor="s")
    ttk.Frame(frame, style="Rule.TFrame", height=1).pack(fill="x", pady=(12, 0))
    return frame


class SegmentedControl(tk.Frame):
    """Selector de una opción entre varias, en una fila de botones unidos.

    options: [(valor, texto)]. El valor elegido vive en `variable`; `command` se llama al cambiar.
    """

    def __init__(self, parent, options: Sequence[Tuple[str, str]], variable: tk.StringVar, command=None) -> None:
        super().__init__(parent, bg=THEME["border_strong"], padx=1, pady=1)
        self.variable = variable
        self.command = command
        self._items = {}
        for idx, (value, text) in enumerate(options):
            label = tk.Label(self, text=text, font=ui_font(10, "bold"), padx=22, pady=8, cursor="hand2")
            label.grid(row=0, column=idx, padx=(0, 1) if idx < len(options) - 1 else 0)
            label.bind("<Button-1>", lambda _e, v=value: self._choose(v))
            self._items[value] = label
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _choose(self, value: str) -> None:
        if self.variable.get() != value:
            self.variable.set(value)
            if self.command:
                self.command()

    def _paint(self) -> None:
        for value, label in self._items.items():
            selected = self.variable.get() == value
            label.configure(bg=THEME["primary"] if selected else THEME["surface"],
                            fg="#ffffff" if selected else THEME["text"])


class QuantityStepper(ttk.Frame):
    """Campo numérico con botones − y + para ajustar la cantidad (mínimo 1)."""

    def __init__(self, parent, variable: tk.StringVar) -> None:
        super().__init__(parent, style="CardInner.TFrame")
        self.variable = variable
        Button(self, text="−", command=lambda: self._step(-1), padx=12).pack(side="left")
        ttk.Entry(self, textvariable=variable, width=6, justify="center").pack(side="left", fill="x", expand=True, padx=6)
        Button(self, text="+", command=lambda: self._step(1), padx=12).pack(side="left")

    def _step(self, delta: int) -> None:
        try:
            current = int(self.variable.get())
        except ValueError:
            current = 1
        self.variable.set(str(max(1, current + delta)))


class StatStrip(ttk.Frame):
    """Franja de cifras clave separadas por líneas finas (en lugar de tarjetas sueltas).

    items: (etiqueta, StringVar, tono) con tono en {"default","warning","danger","success"}.
    """

    def __init__(self, parent, items: Sequence[Tuple[str, tk.StringVar, str]]) -> None:
        super().__init__(parent, style="Card.TFrame")
        tones = {"default": THEME["text"], "warning": THEME["warning"],
                 "danger": THEME["danger"], "success": THEME["success"]}
        for idx, (label, var, tone) in enumerate(items):
            if idx:
                tk.Frame(self, bg=THEME["border"], width=1).grid(row=0, column=2 * idx - 1, sticky="ns", pady=14)
            cell = ttk.Frame(self, style="CardInner.TFrame", padding=(24, 14))
            cell.grid(row=0, column=2 * idx, sticky="nsew")
            self.columnconfigure(2 * idx, weight=1, uniform="stat")
            ttk.Label(cell, text=label, style="StatCaption.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=var, style="StatValue.TLabel",
                      foreground=tones.get(tone, tones["default"])).pack(anchor="w", pady=(2, 0))


class ScrollableFrame(ttk.Frame):
    """Contenedor con scroll vertical; los widgets hijos van en `.body`."""

    def __init__(self, parent) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.canvas = tk.Canvas(self, bg=THEME["bg"], highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, style="Main.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event=None) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel)

    def _unbind_wheel(self, _event=None) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _on_wheel(self, event) -> None:
        if self.body.winfo_height() <= self.canvas.winfo_height():
            return
        num = getattr(event, "num", None)
        step = -1 if num == 4 else 1 if num == 5 else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(step, "units")


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------
def build_tree(parent, columns, height: int = 10):
    """Treeview con scrollbar y etiquetas de fila. Devuelve (contenedor, tree).

    Etiquetas disponibles: even/odd (franjas, se aplican con `stripe_tree`),
    expired/expiring/entry/exit/muted (solo cambian el color del texto).
    """
    box = ttk.Frame(parent, style="Card.TFrame")
    tree = ttk.Treeview(box, columns=columns, show="headings", height=height)
    scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
    scroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
    tree.tag_configure("even", background=THEME["surface"])
    tree.tag_configure("odd", background=THEME["row_alt"])
    tree.tag_configure("expired", foreground=THEME["danger"])
    tree.tag_configure("expiring", foreground=THEME["warning"])
    tree.tag_configure("entry", foreground=THEME["success"])
    tree.tag_configure("exit", foreground=THEME["warning"])
    tree.tag_configure("muted", foreground=THEME["faint"])
    return box, tree


def update_empty_state(tree: ttk.Treeview, text: str = "No hay resultados para mostrar") -> None:
    """Muestra un mensaje centrado sobre la tabla cuando no tiene filas."""
    label = getattr(tree, "_empty_label", None)
    if label is None:
        label = ttk.Label(tree.master, text=text, style="CardMuted.TLabel", font=ui_font(11))
        tree._empty_label = label
    if tree.get_children():
        label.place_forget()
    else:
        label.configure(text=text)
        label.place(relx=0.5, rely=0.55, anchor="center")
        label.lift()


def stripe_tree(tree: ttk.Treeview, special: Optional[Dict[str, str]] = None,
                empty_text: str = "No hay resultados para mostrar") -> None:
    """Franjas alternas + etiqueta de estado opcional por fila (`special[iid]`)."""
    special = special or {}
    for idx, iid in enumerate(tree.get_children()):
        tags = ["odd" if idx % 2 else "even"]
        if iid in special:
            tags.append(special[iid])
        tree.item(iid, tags=tuple(tags))
    update_empty_state(tree, empty_text)


def apply_card_styles(widget, in_card: bool = False) -> None:
    """Los widgets ttk dentro de paneles/pestañas adoptan el fondo del panel."""
    card_variants = {
        "TLabel": "Card.TLabel",
        "TFrame": "CardInner.TFrame",
        "TCheckbutton": "Card.TCheckbutton",
        "TRadiobutton": "Card.TRadiobutton",
    }
    for child in widget.winfo_children():
        child_in_card = in_card
        if isinstance(child, ttk.Widget):
            cls = child.winfo_class()
            current = str(child.cget("style"))
            if cls in ("TLabelframe", "TNotebook") or current == "Card.TFrame":
                child_in_card = True
            elif in_card and not current and cls in card_variants:
                child.configure(style=card_variants[cls])
        apply_card_styles(child, child_in_card)


# ---------------------------------------------------------------------------
# Navegación y marca
# ---------------------------------------------------------------------------
class NavButton(tk.Frame):
    """Elemento de la barra lateral: texto, regla verde a la izquierda si está activo."""

    def __init__(self, parent, text: str, command) -> None:
        super().__init__(parent, bg=THEME["sidebar"], cursor="hand2")
        self.command = command
        self.active = False
        self.rule = tk.Frame(self, width=3, bg=THEME["sidebar"])
        self.rule.pack(side="left", fill="y")
        self.label = tk.Label(self, text=text, font=ui_font(11), anchor="w", bg=THEME["sidebar"],
                              fg=THEME["muted"], padx=18, pady=9)
        self.label.pack(side="left", fill="x", expand=True)
        for w in (self, self.label):
            w.bind("<Enter>", lambda _e: self._paint(hover=True))
            w.bind("<Leave>", lambda _e: self._paint(hover=False))
            w.bind("<Button-1>", lambda _e: self.command())

    def set_active(self, active: bool) -> None:
        self.active = active
        self._paint()

    def _paint(self, hover: bool = False) -> None:
        if self.active:
            bg, fg, rule, weight = THEME["surface"], THEME["primary_dark"], THEME["primary"], "bold"
        elif hover:
            bg, fg, rule, weight = THEME["sidebar_hover"], THEME["text"], THEME["sidebar_hover"], "normal"
        else:
            bg, fg, rule, weight = THEME["sidebar"], THEME["muted"], THEME["sidebar"], "normal"
        self.configure(bg=bg)
        self.rule.configure(bg=rule)
        self.label.configure(bg=bg, fg=fg, font=ui_font(11, weight))


def nav_group_label(parent, text: str) -> tk.Label:
    return tk.Label(parent, text=text.upper(), font=ui_font(8, "bold"), bg=THEME["sidebar"],
                    fg=THEME["faint"], anchor="w")


def draw_logo(parent, size: int, bg: str) -> tk.Canvas:
    """Marca: cuadrado verde con cruz blanca."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, borderwidth=0)
    canvas.create_rectangle(0, 0, size, size, fill=THEME["primary"], outline="")
    arm, thick, c = size * 0.54, size * 0.18, size / 2
    canvas.create_rectangle(c - arm / 2, c - thick / 2, c + arm / 2, c + thick / 2, fill="#ffffff", outline="")
    canvas.create_rectangle(c - thick / 2, c - arm / 2, c + thick / 2, c + arm / 2, fill="#ffffff", outline="")
    return canvas


# ---------------------------------------------------------------------------
# Diálogos modales
# ---------------------------------------------------------------------------
class ModalDialog(tk.Toplevel):
    """Ventana modal centrada sobre su padre. El contenido va en `.body`; `run()` la muestra.

    Se cierra con Escape. Quien la use decide qué hacer al guardar (llamar `destroy()`).
    """

    def __init__(self, parent, title: str, width: int, height: int) -> None:
        super().__init__(parent, bg=THEME["bg"])
        self.title(title)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - width) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.body = ttk.Frame(self, style="Main.TFrame", padding=(28, 24))
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _e: self.destroy())

    def run(self) -> None:
        self.wait_visibility()
        self.grab_set()
        self.wait_window()
