"""Notification utilities for Poke-Saifu.

Handles system sound alerts, Windows desktop toast notifications,
and user preference persistence.
"""

import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Tuple


def get_config_path() -> Path:
    """Get path to config.json in user's home directory."""
    config_dir = Path.home() / ".poke-saifu"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_app_settings() -> dict:
    """Load user preferences (notifications, output dir, auto-save options)."""
    cfg_file = get_config_path()
    defaults = {
        "sound_enabled": True,
        "toast_enabled": True,
        "output_dir": "",
        "save_json": True,
        "save_preview": True,
    }
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update({k: v for k, v in data.items() if k in defaults})
        except Exception:
            pass
    return defaults


def save_app_settings(settings: dict) -> None:
    """Save user preferences to config.json."""
    cfg_file = get_config_path()
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        current = load_app_settings()
        current.update(settings)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_notification_settings() -> Tuple[bool, bool]:
    """Legacy helper for loading notification flags."""
    s = load_app_settings()
    return s["sound_enabled"], s["toast_enabled"]


def save_notification_settings(sound_enabled: bool, toast_enabled: bool) -> None:
    """Legacy helper for saving notification flags."""
    save_app_settings({"sound_enabled": bool(sound_enabled), "toast_enabled": bool(toast_enabled)})


def play_completion_sound() -> None:
    """Play Windows system notification sound using official OS API."""
    if sys.platform != "win32":
        return
    try:
        import winsound

        try:
            # Play standard Windows notification sound asynchronously
            winsound.PlaySound(
                "SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC
            )
        except Exception:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def build_completion_toast_message(
    opponent: str, count: int, total_items: int = 1
) -> str:
    """Build toast notification message formatted for single or batch analysis.

    Single item: 対戦ログ解析完了: ○○との勝負（イベント○件）
    Multiple items: 対戦ログ解析完了: ○○との勝負（ほか計N件）
    """
    opponent_name = opponent if opponent and opponent != "opponent" else "相手"
    if total_items <= 1:
        return f"対戦ログ解析完了: {opponent_name}との勝負（イベント{count}件）"
    else:
        return f"対戦ログ解析完了: {opponent_name}との勝負（ほか計{total_items}件）"


def show_toast_notification(
    title: str = "Poke-Saifu",
    message: str = "対戦ログの解析が完了しました",
) -> None:
    """Display a Windows 10/11 desktop toast notification asynchronously."""
    if sys.platform != "win32":
        return

    def _send_toast():
        try:
            esc_title = title.replace('"', '`"').replace("'", "''")
            esc_msg = message.replace('"', '`"').replace("'", "''")

            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;\n"
                "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;\n"
                "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);\n"
                "$textNodes = $template.GetElementsByTagName('text');\n"
                f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{esc_title}')) | Out-Null;\n"
                f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{esc_msg}')) | Out-Null;\n"
                "$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Poke-Saifu');\n"
                "$notification = [Windows.UI.Notifications.ToastNotification]::new($template);\n"
                "$notifier.Show($notification);\n"
            )

            creation_flags = 0x08000000  # CREATE_NO_WINDOW
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                creationflags=creation_flags,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    threading.Thread(target=_send_toast, daemon=True).start()
