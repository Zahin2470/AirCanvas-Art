from aircanvas.rendering.themes import THEME_ORDER, THEMES, get_theme, next_theme_name


def test_all_four_themes_are_registered():
    assert set(THEMES.keys()) == {"dark", "light", "neon", "monochrome"}


def test_get_theme_returns_the_named_theme():
    assert get_theme("light").name == "light"


def test_get_theme_falls_back_to_dark_for_unknown_name():
    assert get_theme("nonexistent_theme").name == "dark"


def test_next_theme_cycles_through_all_four_and_wraps():
    names = [THEME_ORDER[0]]
    for _ in range(len(THEME_ORDER)):
        names.append(next_theme_name(names[-1]))
    assert names == THEME_ORDER + [THEME_ORDER[0]]  # wraps back to the start


def test_next_theme_of_unknown_name_returns_first_theme():
    assert next_theme_name("something_stale") == THEME_ORDER[0]


def test_every_theme_defines_every_color_field():
    for theme in THEMES.values():
        for field_name in (
            "panel_bg", "toolbar_bg", "status_bg", "border_color", "widget_bg", "widget_selected_bg",
            "widget_border", "widget_border_selected", "widget_text", "status_text", "accent_color", "hover_glow",
        ):
            value = getattr(theme, field_name)
            assert isinstance(value, tuple) and len(value) == 3
            assert all(0 <= c <= 255 for c in value)
