from unittest.mock import patch

from aircanvas.cli import build_arg_parser, main


def test_default_args_have_no_camera_override_and_flags_off():
    args = build_arg_parser().parse_args([])
    assert args.camera is None
    assert args.debug is False
    assert args.mouse is False
    assert args.open is None


def test_camera_flag_parses_as_int():
    args = build_arg_parser().parse_args(["--camera", "2"])
    assert args.camera == 2


def test_debug_and_mouse_are_boolean_flags():
    args = build_arg_parser().parse_args(["--debug", "--mouse"])
    assert args.debug is True
    assert args.mouse is True


def test_open_flag_captures_a_path_string():
    args = build_arg_parser().parse_args(["--open", "my_art.aircanvas"])
    assert args.open == "my_art.aircanvas"


def test_main_calls_app_run_with_parsed_options():
    with patch("aircanvas.cli.app.run", return_value=0) as mock_run:
        code = main(["--mouse", "--open", "sketch.aircanvas"])
    assert code == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["mouse_mode"] is True
    assert kwargs["open_path"] == "sketch.aircanvas"


def test_main_applies_camera_override_to_config():
    with patch("aircanvas.cli.app.run", return_value=0) as mock_run:
        main(["--camera", "3"])
    config = mock_run.call_args[0][0]
    assert config.camera_index == 3


def test_main_returns_apps_exit_code():
    with patch("aircanvas.cli.app.run", return_value=1):
        assert main([]) == 1
