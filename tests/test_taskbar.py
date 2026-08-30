"""Tests for Windows Taskbar Progress module."""

import sys
from unittest.mock import MagicMock
from poke_saifu.taskbar import TaskbarProgress


def test_taskbar_progress_initialization():
    tb = TaskbarProgress()
    if sys.platform == "win32":
        assert tb.is_available or tb._taskbar is None
    else:
        assert not tb.is_available


def test_taskbar_progress_safe_calls_with_none_hwnd():
    tb = TaskbarProgress()
    # All methods should safely handle None or invalid hwnd without throwing exceptions
    tb.set_value(None, 50, 100)
    tb.set_state(None, TaskbarProgress.TBPF_NORMAL)
    tb.set_progress(None, 0.5)
    tb.set_indeterminate(None)
    tb.set_paused(None)
    tb.set_resumed(None)
    tb.set_error(None)
    tb.clear(None)


def test_taskbar_progress_mocked():
    tb = TaskbarProgress()
    mock_val_fn = MagicMock()
    mock_state_fn = MagicMock()

    tb._taskbar = 12345
    tb._set_progress_value_fn = mock_val_fn
    tb._set_progress_state_fn = mock_state_fn

    # Test set_progress
    tb.set_progress(999, 0.45)
    mock_state_fn.assert_called_with(12345, 999, TaskbarProgress.TBPF_NORMAL)
    mock_val_fn.assert_called_with(12345, 999, 450, 1000)

    # Test paused progress
    tb.set_progress(999, 0.45, paused=True)
    mock_state_fn.assert_called_with(12345, 999, TaskbarProgress.TBPF_PAUSED)

    # Test clear
    tb.clear(999)
    mock_state_fn.assert_called_with(12345, 999, TaskbarProgress.TBPF_NOPROGRESS)

    # Test error
    tb.set_error(999)
    mock_state_fn.assert_called_with(12345, 999, TaskbarProgress.TBPF_ERROR)
    mock_val_fn.assert_called_with(12345, 999, 1000, 1000)
