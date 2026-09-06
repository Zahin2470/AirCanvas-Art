from pathlib import Path

from aircanvas.config import AppConfig, get_app_data_dir, load_config


def test_defaults_are_sane():
    cfg = AppConfig()
    assert cfg.camera_index == 0
    assert cfg.camera_width > 0 and cfg.camera_height > 0
    assert cfg.max_num_hands >= 1
    assert cfg.debug is False


def test_load_config_applies_overrides_without_mutating_defaults():
    cfg = load_config({"camera_index": 2, "debug": True})
    assert cfg.camera_index == 2
    assert cfg.debug is True
    assert AppConfig().camera_index == 0  # base defaults untouched


def test_load_config_with_no_overrides_returns_defaults():
    assert load_config(None) == AppConfig()
    assert load_config({}) == AppConfig()


def test_load_config_ignores_unknown_keys():
    cfg = load_config({"totally_made_up_key": 123, "camera_index": 1})
    assert cfg.camera_index == 1
    assert not hasattr(cfg, "totally_made_up_key")


def test_load_config_ignores_none_values():
    cfg = load_config({"camera_index": None})
    assert cfg.camera_index == AppConfig().camera_index


def test_app_data_dir_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AIRCANVAS_HOME", str(tmp_path))
    assert get_app_data_dir() == tmp_path


def test_app_data_dir_defaults_under_home(monkeypatch):
    monkeypatch.delenv("AIRCANVAS_HOME", raising=False)
    assert str(get_app_data_dir()).startswith(str(Path.home()))
