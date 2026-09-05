import os

from wdpassport import omarchy


SAMPLE = b'''
mode = "dark"
accent = "#7aa2f7"
background = "#1a1b26"
lighter_background = "#24283b"
foreground = "#a9b1d6"
dark_foreground = "#565f89"
red = "#f7768e"
green = "#9ece6a"
yellow = "#e0af68"
'''


def _theme(tmp_path, body=SAMPLE):
    d = tmp_path / "omarchy" / "current" / "theme"
    d.mkdir(parents=True)
    (d / "colors.toml").write_bytes(body)
    (d.parent / "theme.name").write_text("tokyo-night\n")
    return tmp_path


def test_detects_omarchy_from_state_dir(tmp_path, monkeypatch):
    _theme(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert omarchy.theme_dir().endswith("omarchy/current/theme")
    assert omarchy.theme_name() == "tokyo-night"


def test_absent_off_omarchy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("OMARCHY_PATH", raising=False)
    monkeypatch.setattr(omarchy.shutil, "which", lambda n: None)
    assert omarchy.theme_dir() == ""
    assert not omarchy.is_omarchy()


def test_loads_palette(tmp_path, monkeypatch):
    _theme(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    colors = omarchy.load_colors()
    assert colors["accent"] == "#7aa2f7"
    assert colors["background"] == "#1a1b26"


def test_falls_back_when_colors_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    colors = omarchy.load_colors()
    assert colors["accent"]  # fallback palette is always well-formed


def test_malformed_toml_does_not_raise(tmp_path, monkeypatch):
    _theme(tmp_path, b"this is not valid toml {{{")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert omarchy.load_colors()["accent"]


def test_css_uses_theme_colors(tmp_path, monkeypatch):
    _theme(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    css = omarchy.gtk_css()
    assert "#7aa2f7" in css      # accent
    assert "#1a1b26" in css      # background
    assert ".locked" in css and ".unlocked" in css
    assert css.count("{") == css.count("}")


def test_css_is_valid_without_a_theme(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    css = omarchy.gtk_css()
    assert css.count("{") == css.count("}")


def test_prefers_dark_follows_mode(tmp_path, monkeypatch):
    _theme(tmp_path, SAMPLE.replace(b'mode = "dark"', b'mode = "light"'))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert not omarchy.prefers_dark()


def test_non_string_values_are_ignored(tmp_path, monkeypatch):
    _theme(tmp_path, SAMPLE + b'\n[extra]\nnested = "x"\n')
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    colors = omarchy.load_colors()
    assert all(isinstance(v, str) for v in colors.values())
