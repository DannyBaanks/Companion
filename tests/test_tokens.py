"""Tests for design tokens and presentation themes."""

from companion.tokens import (
    Color,
    DARK,
    LIGHT,
    SOFT_NEON,
    Motion,
    Radii,
    Shadows,
    Spacing,
    StateVisual,
    Theme,
    Typography,
    get_theme,
)


def test_color_rgb_extracts_correct_channels():
    c = Color("#ff8000")
    assert c.rgb == (255, 128, 0)


def test_color_with_alpha_preserves_hex():
    c = Color("#112233")
    c2 = c.with_alpha(0.5)
    assert c2.hex == "#112233"
    assert c2.alpha == 0.5


def test_typography_defaults():
    t = Typography()
    assert t.font_family
    assert t.size_name < t.size_body < t.size_title


def test_spacing_is_monotonic():
    s = Spacing()
    assert s.xxs < s.xs < s.sm < s.md < s.lg < s.xl < s.xxl


def test_radii_monotonic():
    r = Radii()
    assert r.none < r.sm < r.md < r.lg < r.pill


def test_all_built_in_themes_have_all_six_states():
    for theme in (DARK, LIGHT, SOFT_NEON):
        assert set(theme.states.keys()) == {"idle", "thinking", "working", "success", "error", "waiting"}


def test_all_states_have_non_empty_accent_and_icon():
    for theme in (DARK, LIGHT, SOFT_NEON):
        for name, sv in theme.states.items():
            assert sv.accent, f"{theme.name}/{name} missing accent"
            assert sv.icon, f"{theme.name}/{name} missing icon"


def test_get_theme_returns_built_in_by_name():
    assert get_theme("dark") is DARK
    assert get_theme("light") is LIGHT
    assert get_theme("soft-neon") is SOFT_NEON


def test_get_theme_falls_back_to_dark_for_unknown():
    assert get_theme("nope") is DARK


def test_themes_are_distinct():
    """Each built-in theme has different bubble/menu background."""
    assert DARK.bg_bubble != LIGHT.bg_bubble
    assert DARK.bg_bubble != SOFT_NEON.bg_bubble
    assert LIGHT.bg_bubble != SOFT_NEON.bg_bubble


def test_theme_has_typography_spacing_radii_shadows_motion():
    for theme in (DARK, LIGHT, SOFT_NEON):
        assert isinstance(theme.typography, Typography)
        assert isinstance(theme.spacing, Spacing)
        assert isinstance(theme.radii, Radii)
        assert isinstance(theme.shadows, Shadows)
        assert isinstance(theme.motion, Motion)
        assert theme.motion.poll_ms > 0


def test_dark_stage_is_magenta_transparent():
    assert DARK.bg_stage == "magenta"


def test_light_fg_primary_is_dark_text():
    assert LIGHT.fg_primary.startswith("#")
    r, g, b = int(LIGHT.fg_primary[1:3], 16), int(LIGHT.fg_primary[3:5], 16), int(LIGHT.fg_primary[5:7], 16)
    # Light theme text should be dark (sum of channels < 384)
    assert r + g + b < 384


def test_soft_neon_fg_primary_is_light_text():
    assert SOFT_NEON.fg_primary.startswith("#")
    r, g, b = (
        int(SOFT_NEON.fg_primary[1:3], 16),
        int(SOFT_NEON.fg_primary[3:5], 16),
        int(SOFT_NEON.fg_primary[5:7], 16),
    )
    # Soft-neon text should be light (sum of channels > 384)
    assert r + g + b > 384


def test_tk_surface_colors_use_rgb_without_css_alpha():
    """Tk accepts #rrggbb, not CSS #rrggbbaa colors."""
    for theme in (DARK, LIGHT, SOFT_NEON):
        for value in (theme.bg_stage, theme.bg_bubble, theme.bg_menu,
                      theme.bg_menu_hover, theme.bg_menu_disabled,
                      theme.fg_primary, theme.fg_secondary, theme.fg_bubble,
                      theme.fg_accent, theme.border_bubble, theme.border_focus):
            assert value == "magenta" or len(value) == 7, (theme.name, value)


def test_config_theme_defaults_to_dark():
    """CompanionConfig.theme defaults to dark."""
    from companion.config import CompanionConfig

    cfg = CompanionConfig()
    assert cfg.theme == "dark"
