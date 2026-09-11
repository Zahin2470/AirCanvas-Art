import json

from aircanvas.persistence.settings import AppSettings, load_settings, save_settings


def test_defaults_are_sane():
    settings = AppSettings()
    assert settings.theme == "dark"
    assert 0.0 <= settings.master_volume <= 1.0
    assert settings.mirror is True


def test_load_missing_file_returns_defaults(tmp_path):
    loaded = load_settings(tmp_path / "nope.json")
    assert loaded == AppSettings()


def test_round_trip_preserves_all_fields(tmp_path):
    path = tmp_path / "settings.json"
    original = AppSettings(
        theme="neon", brush_type_index=2, color_index=3, size_index=4,
        mirror=False, particles_enabled=False, master_volume=0.4, sfx_volume=0.9, muted=True,
    )
    save_settings(original, path)
    loaded = load_settings(path)
    assert loaded == original


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json")
    assert load_settings(path) == AppSettings()


def test_load_non_object_json_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps([1, 2, 3]))
    assert load_settings(path) == AppSettings()


def test_load_ignores_unknown_fields_for_forward_compatibility(tmp_path):
    path = tmp_path / "settings.json"
    payload = {"version": 1, "theme": "light", "some_future_field": "xyz"}
    path.write_text(json.dumps(payload))
    loaded = load_settings(path)
    assert loaded.theme == "light"


def test_load_clamps_out_of_range_volume(tmp_path):
    path = tmp_path / "settings.json"
    payload = {"version": 1, "master_volume": 400.0, "sfx_volume": -5.0}
    path.write_text(json.dumps(payload))
    loaded = load_settings(path)
    assert loaded.master_volume == 1.0
    assert loaded.sfx_volume == 0.0


def test_load_invalid_field_type_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    payload = {"version": 1, "master_volume": "not-a-number"}
    path.write_text(json.dumps(payload))
    assert load_settings(path) == AppSettings()


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "settings.json"
    save_settings(AppSettings(), path)
    assert path.exists()


def test_save_is_atomic_no_leftover_tmp_file(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(AppSettings(), path)
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_clamped_fixes_negative_indices():
    settings = AppSettings(brush_type_index=-3, color_index=-1, size_index=-2)
    clamped = settings.clamped()
    assert clamped.brush_type_index == 0
    assert clamped.color_index == 0
    assert clamped.size_index == 0
