"""Unit tests for notifier module and taskbar flash integration."""

from pathlib import Path
import pytest
from poke_saifu.notifier import (
    build_completion_toast_message,
    load_app_settings,
    load_notification_settings,
    play_completion_sound,
    save_app_settings,
    save_notification_settings,
    show_toast_notification,
)
from poke_saifu.taskbar import TaskbarProgress


def test_build_completion_toast_message_single():
    msg1 = build_completion_toast_message("シゲル", 12, total_items=1)
    assert msg1 == "対戦ログ解析完了: シゲルとの勝負（イベント12件）"

    # Default total_items=1
    msg2 = build_completion_toast_message("ワタル", 5)
    assert msg2 == "対戦ログ解析完了: ワタルとの勝負（イベント5件）"

    # Fallback opponent name
    msg3 = build_completion_toast_message("opponent", 3, total_items=1)
    assert msg3 == "対戦ログ解析完了: 相手との勝負（イベント3件）"

    msg4 = build_completion_toast_message("", 0, total_items=1)
    assert msg4 == "対戦ログ解析完了: 相手との勝負（イベント0件）"


def test_build_completion_toast_message_multiple():
    msg1 = build_completion_toast_message("シゲル", 12, total_items=5)
    assert msg1 == "対戦ログ解析完了: シゲルとの勝負（ほか計5件）"

    msg2 = build_completion_toast_message("opponent", 8, total_items=3)
    assert msg2 == "対戦ログ解析完了: 相手との勝負（ほか計3件）"


def test_notification_settings_persistence(tmp_path, monkeypatch):
    test_config_file = tmp_path / ".poke-saifu" / "config.json"
    monkeypatch.setattr("poke_saifu.notifier.get_config_path", lambda: test_config_file)

    # Defaults when no file exists
    s, t = load_notification_settings()
    assert s is True
    assert t is True

    # Save false settings
    save_notification_settings(sound_enabled=False, toast_enabled=True)
    s2, t2 = load_notification_settings()
    assert s2 is False
    assert t2 is True

    save_notification_settings(sound_enabled=False, toast_enabled=False)
    s3, t3 = load_notification_settings()
    assert s3 is False
    assert t3 is False


def test_app_settings_persistence(tmp_path, monkeypatch):
    test_config_file = tmp_path / ".poke-saifu" / "config.json"
    monkeypatch.setattr("poke_saifu.notifier.get_config_path", lambda: test_config_file)

    # Defaults
    defaults = load_app_settings()
    assert defaults["sound_enabled"] is True
    assert defaults["toast_enabled"] is True
    assert defaults["output_dir"] == ""
    assert defaults["save_json"] is True
    assert defaults["save_preview"] is True

    # Save custom
    save_app_settings(
        {
            "output_dir": "C:/PokemonLogs",
            "save_preview": False,
        }
    )
    loaded = load_app_settings()
    assert loaded["output_dir"] == "C:/PokemonLogs"
    assert loaded["save_json"] is True
    assert loaded["save_preview"] is False
    assert loaded["sound_enabled"] is True


def test_play_completion_sound_safe():
    # Should execute safely without raising exception
    play_completion_sound()


def test_show_toast_notification_safe():
    # Should execute safely in background thread without error
    show_toast_notification(title="Test", message="Test Message")


def test_taskbar_flash_safe():
    taskbar = TaskbarProgress()
    # Should handle None or invalid hwnd gracefully
    taskbar.flash(None)
    taskbar.flash(0)
    taskbar.flash(12345)
