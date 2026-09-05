"""Omarchy desktop integration.

Omarchy (an Arch/Hyprland distribution) publishes the active theme's palette
as a small TOML file and re-points it whenever the user switches themes. Apps
that read it look native instead of shipping their own hardcoded colours.

Everything here degrades to no-ops off Omarchy, so the GUI and tray keep their
stock appearance on other desktops.
"""

import os
import shutil

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - older interpreters
    tomllib = None


# Omarchy re-points this symlink on every theme switch.
_THEME_LINK = "omarchy/current/theme"

# Fallback palette (GNOME Adwaita) so the CSS is always well-formed.
_FALLBACK = {
    "mode": "dark",
    "accent": "#3584e4",
    "background": "#1e1e1e",
    "lighter_background": "#2a2a2a",
    "foreground": "#deddda",
    "dark_foreground": "#9a9996",
    "red": "#e01b24",
    "green": "#2ec27e",
    "yellow": "#f5c211",
}


def state_home() -> str:
    return os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")


def theme_dir() -> str:
    """Path to the active Omarchy theme directory, or "" if not on Omarchy."""
    path = os.path.join(state_home(), _THEME_LINK)
    return path if os.path.isdir(path) else ""


def is_omarchy() -> bool:
    """True when running on an Omarchy desktop."""
    if os.environ.get("OMARCHY_PATH") or shutil.which("omarchy"):
        return True
    return bool(theme_dir())


def theme_name() -> str:
    """Name of the active theme (e.g. "tokyo-night"), or "" if unknown."""
    path = os.path.join(state_home(), "omarchy", "current", "theme.name")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def load_colors() -> dict:
    """Read the active theme's palette, falling back to a sane default."""
    colors = dict(_FALLBACK)
    directory = theme_dir()
    if not directory or tomllib is None:
        return colors
    try:
        with open(os.path.join(directory, "colors.toml"), "rb") as fh:
            parsed = tomllib.load(fh)
    except (OSError, ValueError):
        return colors
    # Keep only string values; the file is user-editable and may carry tables.
    colors.update({k: v for k, v in parsed.items() if isinstance(v, str)})
    return colors


def _color(colors: dict, *names: str) -> str:
    """First present colour among names, else the fallback accent."""
    for name in names:
        value = colors.get(name)
        if value:
            return value
    return _FALLBACK["accent"]


def gtk_css(colors: dict = None) -> str:
    """GTK CSS painting the app in the active Omarchy theme.

    Shared by the GTK4 control panel and the GTK3 tray dialogs; both use the
    same class names, so one stylesheet covers each.
    """
    c = colors if colors is not None else load_colors()

    accent = _color(c, "accent", "blue")
    bg = _color(c, "background")
    raised = _color(c, "lighter_background", "selection", "background")
    fg = _color(c, "foreground", "light_foreground")
    dim = _color(c, "dark_foreground", "muted")
    locked = _color(c, "red", "bright_red")
    unlocked = _color(c, "green", "bright_green")
    warn = _color(c, "yellow", "orange")

    return """
    window, dialog {{ background-color: {bg}; color: {fg}; }}
    label {{ color: {fg}; }}
    .dim-label, .subtitle {{ color: {dim}; }}

    .locked   {{ color: {locked}; font-weight: bold; }}
    .unlocked {{ color: {unlocked}; font-weight: bold; }}
    .warning  {{ color: {warn}; }}

    .drive-badge {{
        padding: 4px 10px;
        border-radius: 6px;
        background-color: {raised};
    }}

    button {{
        background-color: {raised};
        color: {fg};
        border-radius: 6px;
    }}
    button:hover {{ background-color: {accent}; color: {bg}; }}
    button.suggested-action {{ background-color: {accent}; color: {bg}; }}
    button.destructive-action {{ background-color: {locked}; color: {bg}; }}

    entry {{
        background-color: {raised};
        color: {fg};
        border-radius: 6px;
    }}
    entry:focus {{ border-color: {accent}; }}

    headerbar {{ background-color: {raised}; color: {fg}; }}
    """.format(bg=bg, fg=fg, dim=dim, raised=raised, accent=accent,
               locked=locked, unlocked=unlocked, warn=warn)


def prefers_dark() -> bool:
    """True when the active Omarchy theme is a dark one."""
    return str(load_colors().get("mode", "dark")).lower() != "light"


def watch_theme(on_change) -> object:
    """Call on_change() whenever the user switches Omarchy theme.

    Returns the GLib file monitor (the caller must keep a reference) or None
    if watching is unavailable. Failure here is cosmetic, never fatal.
    """
    directory = os.path.join(state_home(), "omarchy", "current")
    if not os.path.isdir(directory):
        return None
    try:
        from gi.repository import Gio
    except (ImportError, ValueError):
        return None
    try:
        monitor = Gio.File.new_for_path(directory).monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
    except Exception:
        return None
    monitor.connect("changed", lambda *_args: on_change())
    return monitor
