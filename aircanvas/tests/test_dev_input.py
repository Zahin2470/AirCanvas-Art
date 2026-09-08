from aircanvas.interaction.dev_input import DevIntentSource
from aircanvas.interaction.state_machine import IntentState, StateMachineConfig


def _source(**overrides):
    return DevIntentSource(StateMachineConfig(debounce_frames=1, **overrides))


def test_cursor_outside_area_reports_no_cursor():
    source = _source()
    result = source.update(cursor_pos=None, left_button=False, right_button=False, fist_key=False)
    assert result.cursor_pos is None
    assert result.is_drawing is False


def test_no_buttons_held_is_pointer_active_only():
    source = _source()
    result = source.update((10, 10), left_button=False, right_button=False, fist_key=False)
    assert result.state == IntentState.POINTER_ACTIVE
    assert result.cursor_pos == (10, 10)


def test_left_button_held_draws():
    source = _source()
    result = source.update((10, 10), left_button=True, right_button=False, fist_key=False)
    assert result.is_drawing is True
    assert result.stroke_started is True


def test_right_button_held_erases():
    source = _source()
    result = source.update((10, 10), left_button=False, right_button=True, fist_key=False)
    assert result.is_erasing is True
    assert result.erase_started is True


def test_releasing_left_button_ends_the_stroke():
    source = _source()
    source.update((10, 10), left_button=True, right_button=False, fist_key=False)
    result = source.update((10, 10), left_button=False, right_button=False, fist_key=False)
    assert result.is_drawing is False
    assert result.stroke_ended is True


def test_releasing_right_button_ends_the_erase():
    source = _source()
    source.update((10, 10), left_button=False, right_button=True, fist_key=False)
    result = source.update((10, 10), left_button=False, right_button=False, fist_key=False)
    assert result.is_erasing is False
    assert result.erase_ended is True


def test_fist_key_held_long_enough_confirms_clear():
    source = _source(fist_confirm_frames=3)
    flags = []
    for _ in range(3):
        flags.append(source.update((10, 10), False, False, True).clear_confirmed)
    assert flags.count(True) == 1
    assert flags[-1] is True


def test_reset_returns_to_idle():
    source = _source()
    source.update((10, 10), True, False, False)
    source.reset()
    result = source.update(None, False, False, False)
    assert result.state == IntentState.IDLE
