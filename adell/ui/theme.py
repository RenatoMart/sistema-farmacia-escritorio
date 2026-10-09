"""Identidad visual de la aplicación: colores, tipografías y estilos ttk.

Interfaz pública (todo lo demás es detalle interno):
    THEME                 diccionario de colores (única fuente de verdad)
    ui_font(size, weight) fuente de texto (sans) lista para usar en `font=`
    display_font(size, weight) fuente de títulos (serif)
    configure_style(root) registra todos los estilos ttk; llamar una vez tras crear la raíz

Las familias tipográficas se resuelven la primera vez que se piden, porque
`tkinter.font.families()` necesita que ya exista una ventana raíz.
"""
from tkinter import font as tkfont
from tkinter import ttk

THEME = {
    "bg": "#f3f0e8",            # papel: fondo de la aplicación
    "surface": "#fdfcf9",       # paneles y tablas
    "sidebar": "#ebe7dc",
    "sidebar_hover": "#e2ddcf",
    "border": "#dcd7ca",        # línea fina
    "border_strong": "#bdb7a6",
    "text": "#1b2420",          # tinta
    "muted": "#66705f",
    "faint": "#98a090",
    "primary": "#1d5c4a",       # verde farmacia, sobrio
    "primary_dark": "#154538",
    "primary_soft": "#dfeae3",
    "danger": "#a63d2a",
    "danger_soft": "#f6e6e1",
    "warning": "#946212",
    "success": "#2f7d5b",
    "row_alt": "#f8f6f0",
}

_SANS = ("Segoe UI", "Inter", "SF Pro Text", "Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans", "Helvetica")
_SERIF = ("Georgia", "Source Serif 4", "Noto Serif", "DejaVu Serif", "Times New Roman")
_families = {}


def _pick(candidates, fallback):
    available = set(tkfont.families())
    return next((f for f in candidates if f in available), fallback)


def _family(kind: str) -> str:
    if kind not in _families:
        _families["sans"] = _pick(_SANS, "TkDefaultFont")
        _families["serif"] = _pick(_SERIF, _families["sans"])
    return _families[kind]


def ui_font(size: int = 10, weight: str = "normal"):
    return (_family("sans"), size, weight)


def display_font(size: int = 20, weight: str = "bold"):
    return (_family("serif"), size, weight)


def configure_style(root) -> None:
    t = THEME
    sans = _family("sans")

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        tkfont.nametofont(name).configure(family=sans, size=10)

    root.configure(bg=t["bg"])
    root.option_add("*Toplevel.background", t["bg"])
    root.option_add("*TCombobox*Listbox.font", ui_font(10))
    root.option_add("*TCombobox*Listbox.background", t["surface"])
    root.option_add("*TCombobox*Listbox.foreground", t["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["primary"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    style = ttk.Style(root)
    style.theme_use("clam")

    # --- Contenedores -------------------------------------------------------
    style.configure("TFrame", background=t["bg"])
    style.configure("Main.TFrame", background=t["bg"])
    style.configure("Card.TFrame", background=t["surface"], relief="solid", borderwidth=1,
                    bordercolor=t["border"], lightcolor=t["border"], darkcolor=t["border"])
    style.configure("CardInner.TFrame", background=t["surface"], borderwidth=0, relief="flat")
    style.configure("Rule.TFrame", background=t["border"])
    style.configure("TLabelframe", background=t["surface"], relief="flat", borderwidth=0,
                    bordercolor=t["surface"], lightcolor=t["surface"], darkcolor=t["surface"])
    style.configure("TLabelframe.Label", background=t["surface"], foreground=t["text"], font=display_font(13, "bold"))

    # --- Etiquetas ----------------------------------------------------------
    style.configure("TLabel", background=t["bg"], foreground=t["text"], font=ui_font(10))
    style.configure("Card.TLabel", background=t["surface"], foreground=t["text"], font=ui_font(10))
    style.configure("CardMuted.TLabel", background=t["surface"], foreground=t["muted"], font=ui_font(9))
    style.configure("Muted.TLabel", background=t["bg"], foreground=t["muted"], font=ui_font(9))
    style.configure("Header.TLabel", background=t["bg"], foreground=t["text"], font=display_font(24, "bold"))
    style.configure("Subtitle.TLabel", background=t["bg"], foreground=t["muted"], font=ui_font(10))
    style.configure("Field.TLabel", background=t["surface"], foreground=t["muted"], font=ui_font(9))
    style.configure("FilterField.TLabel", background=t["bg"], foreground=t["muted"], font=ui_font(9))
    style.configure("StatCaption.TLabel", background=t["surface"], foreground=t["muted"], font=ui_font(9))
    style.configure("StatValue.TLabel", background=t["surface"], foreground=t["text"], font=ui_font(24, "bold"))

    # --- Tablas -------------------------------------------------------------
    style.configure("Treeview", background=t["surface"], fieldbackground=t["surface"], foreground=t["text"],
                    rowheight=34, font=ui_font(10), borderwidth=0, relief="flat")
    style.configure("Treeview.Heading", background=t["sidebar"], foreground=t["muted"], relief="flat",
                    font=ui_font(9, "bold"), padding=(10, 9), borderwidth=0)
    style.map("Treeview", background=[("selected", t["primary_soft"])], foreground=[("selected", t["primary_dark"])])
    style.map("Treeview.Heading", background=[("active", t["sidebar_hover"])])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # --- Formularios --------------------------------------------------------
    style.configure("TEntry", fieldbackground=t["surface"], foreground=t["text"], padding=(9, 7),
                    bordercolor=t["border_strong"], lightcolor=t["border_strong"], darkcolor=t["border_strong"],
                    insertcolor=t["text"])
    style.map("TEntry",
              bordercolor=[("focus", t["primary"])], lightcolor=[("focus", t["primary"])],
              darkcolor=[("focus", t["primary"])],
              fieldbackground=[("disabled", t["row_alt"])], foreground=[("disabled", t["muted"])])
    style.configure("TCombobox", fieldbackground=t["surface"], background=t["sidebar"], foreground=t["text"],
                    padding=(9, 7), arrowsize=14, arrowcolor=t["muted"],
                    bordercolor=t["border_strong"], lightcolor=t["border_strong"], darkcolor=t["border_strong"])
    style.map("TCombobox",
              fieldbackground=[("readonly", t["surface"]), ("disabled", t["row_alt"])],
              selectbackground=[("readonly", t["surface"])],
              selectforeground=[("readonly", t["text"])],
              bordercolor=[("focus", t["primary"])], lightcolor=[("focus", t["primary"])],
              darkcolor=[("focus", t["primary"])])
    for name, bg in (("TCheckbutton", t["bg"]), ("Card.TCheckbutton", t["surface"]),
                     ("TRadiobutton", t["bg"]), ("Card.TRadiobutton", t["surface"])):
        style.configure(name, background=bg, foreground=t["text"], font=ui_font(10), focuscolor=bg)
        style.map(name, background=[("active", bg)], indicatorcolor=[("selected", t["primary"])])

    # --- Pestañas y scrollbars ---------------------------------------------
    style.configure("TNotebook", background=t["surface"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=t["surface"], foreground=t["muted"], padding=(16, 9),
                    font=ui_font(10, "bold"), borderwidth=0)
    style.map("TNotebook.Tab",
              foreground=[("selected", t["primary"]), ("active", t["text"])],
              background=[("selected", t["surface"]), ("active", t["surface"])],
              padding=[("selected", (16, 9))], expand=[("selected", (0, 0, 0, 0))],
              lightcolor=[("selected", t["primary"])])
    style.configure("TScrollbar", background=t["border"], troughcolor=t["row_alt"], bordercolor=t["row_alt"],
                    lightcolor=t["border"], darkcolor=t["border"], arrowcolor=t["muted"], relief="flat", arrowsize=13)
    style.map("TScrollbar", background=[("active", t["border_strong"])])
    style.configure("TSeparator", background=t["border"])
