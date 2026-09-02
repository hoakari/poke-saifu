"""GUI application for Poke-Saifu.

Provides Drag & Drop file input, processing progress feedback,
JSON preview with copy action, and customized save dialog.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, List, Optional, Tuple
import cv2
import numpy as np

# Attempt to load TkinterDnD for drag and drop support
HAS_DND = False
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    BaseTk = TkinterDnD.Tk
    HAS_DND = True
except ImportError:
    BaseTk = tk.Tk

from poke_saifu.notifier import (
    build_completion_toast_message,
    load_app_settings,
    play_completion_sound,
    save_app_settings,
    show_toast_notification,
)
from poke_saifu.parser import BattleParser
from poke_saifu.queue_manager import QueueItem, QueueManager, QueueStatus
from poke_saifu.taskbar import TaskbarProgress


def get_asset_path(filename: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller temp directory
        base_path = Path(sys._MEIPASS)
        candidate = base_path / "poke_saifu" / "assets" / filename
        if candidate.exists():
            return candidate
        return base_path / "assets" / filename
    # Normal dev environment
    dev_path = Path(__file__).parent / "assets" / filename
    if dev_path.exists():
        return dev_path
    return Path(__file__).parent.parent / "assets" / filename


class PokeSaifuApp(BaseTk):
    """Main desktop application window for Poke-Saifu."""

    def __init__(self):
        super().__init__()
        self.title("Poke-Saifu - ポケモン対戦ログ抽出")
        self.geometry("820x760")
        self.minsize(680, 560)

        # Set window icons
        self._setup_window_icon()

        # Apply system theme styling
        self._setup_styles()

        self.parser = BattleParser()
        self.taskbar = TaskbarProgress()
        self.queue_mgr = QueueManager()

        # Load user application preferences
        app_settings = load_app_settings()
        self.sound_enabled_var = tk.BooleanVar(value=app_settings["sound_enabled"])
        self.toast_enabled_var = tk.BooleanVar(value=app_settings["toast_enabled"])
        self.dest_dir_var = tk.StringVar(value=app_settings["output_dir"])
        self.chk_save_json_var = tk.BooleanVar(value=app_settings["save_json"])
        self.chk_save_preview_var = tk.BooleanVar(value=app_settings["save_preview"])
        self.last_saved_output_dir: str = app_settings["output_dir"]

        self.current_json: str = ""
        self.current_preview_frame: Optional[np.ndarray] = None
        self._preview_photo_image: Any = None
        self.default_filename: str = f"{datetime.now().strftime('%Y-%m-%d')}_vs_opponent.json"
        self._is_processing: bool = False
        self._is_paused: bool = False
        self._is_queue_open: bool = False
        self._current_queue_item: Optional[QueueItem] = None
        self._drag_data: dict = {"item_id": None, "index": None}
        self._batch_session_total: int = 0
        self._batch_last_opponent: str = ""
        self._batch_last_events_count: int = 0
        self._current_session_id: int = 0
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        self._build_ui()

    def _get_root_hwnd(self) -> Optional[int]:
        """Get the root Windows HWND of the main window for taskbar integration."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            hwnd = self.winfo_id()
            root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
            return root_hwnd if root_hwnd else hwnd
        except Exception:
            return None

    def _setup_window_icon(self):
        # 1. Windows taskbar icon fix: tell Windows this is a distinct app, not generic python.exe
        if sys.platform == "win32":
            try:
                import ctypes
                myappid = "pokesaifu.battleparser.desktop.v1"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        ico_path = get_asset_path("icon.ico")
        png_path = get_asset_path("icon.png")

        if ico_path.exists():
            try:
                self.iconbitmap(default=str(ico_path))
            except Exception:
                pass

        if png_path.exists():
            try:
                self._app_icon_img = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._app_icon_img)
            except Exception:
                pass

    def _setup_styles(self):
        self.style = ttk.Style(self)
        available_themes = self.style.theme_names()
        if "vista" in available_themes:
            self.style.theme_use("vista")
        elif "clam" in available_themes:
            self.style.theme_use("clam")

        # Configure consistent typography and button padding
        self.style.configure("TButton", font=("Segoe UI", 9), padding=(10, 4))
        self.style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(12, 4))
        self.style.configure("TLabel", font=("Segoe UI", 9))
        self.style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))

    def _build_ui(self):
        # Top Menu Bar
        menubar = tk.Menu(self)
        menu_notification = tk.Menu(menubar, tearoff=0)
        menu_notification.add_checkbutton(
            label="完了通知音 (SE)",
            variable=self.sound_enabled_var,
            command=self._on_notification_setting_change,
        )
        menu_notification.add_checkbutton(
            label="デスクトップ通知 (トースト)",
            variable=self.toast_enabled_var,
            command=self._on_notification_setting_change,
        )
        menubar.add_cascade(label="通知(N)", menu=menu_notification)
        self.config(menu=menubar)

        # Split pane container for main and queue panel
        self.pane_container = ttk.Frame(self)
        self.pane_container.pack(fill="both", expand=True)

        # Left Container with padding
        self.main_container = ttk.Frame(self.pane_container, padding="15 15 15 15")
        self.main_container.pack(side="left", fill="both", expand=True)

        # Right Queue Panel (collapsible)
        self.queue_panel = ttk.Frame(self.pane_container, padding="10 15 15 15", width=330)
        self._build_queue_panel()

        # 1. Top Section: Drop Zone & Browse Buttons
        drop_frame = ttk.LabelFrame(self.main_container, text=" 解析対象の選択 (動画 / スクショ画像) ", padding="10")
        drop_frame.pack(fill="x", pady=(0, 10))

        self.initial_dnd_text = "ここに動画ファイル (.mp4 / .mov / .avi / .mkv) または画像群をドラッグ＆ドロップ\nまたは右側のボタンから選択"
        if not HAS_DND:
            self.initial_dnd_text = "右側の [動画を選択] または [画像群を選択] ボタンから対象ファイルを選択してください"

        self.drop_label = tk.Label(
            drop_frame,
            text=self.initial_dnd_text,
            bg="#EBF3FA",
            fg="#2C3E50",
            font=("Segoe UI", 10),
            relief="groove",
            bd=2,
            height=4,
            cursor="hand2",
        )
        self.drop_label.pack(fill="x", expand=True, side="left", padx=(0, 10))

        if HAS_DND:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_label.bind("<Enter>", lambda e: self.drop_label.config(bg="#D6EAF8"))
            self.drop_label.bind("<Leave>", lambda e: self.drop_label.config(bg="#EBF3FA"))

        self.drop_label.bind("<Button-1>", lambda e: self._browse_video())

        btn_box = ttk.Frame(drop_frame)
        btn_box.pack(side="right", fill="y")

        self.btn_browse_video = ttk.Button(
            btn_box,
            text="動画を選択...",
            command=self._browse_video,
        )
        self.btn_browse_video.pack(fill="x", pady=(0, 4))

        self.btn_browse_images = ttk.Button(
            btn_box,
            text="画像群を選択...",
            command=self._browse_images,
        )
        self.btn_browse_images.pack(fill="x", pady=(0, 4))

        self.btn_toggle_queue = ttk.Button(
            btn_box,
            text="📋 キュー",
            command=self._toggle_queue_panel,
        )
        self.btn_toggle_queue.pack(fill="x")

        # 2. Middle Section: Progress & Status
        status_frame = ttk.Frame(self.main_container)
        status_frame.pack(fill="x", pady=(0, 8))

        self.progress_bar = ttk.Progressbar(
            status_frame,
            orient="horizontal",
            mode="determinate",
        )
        self.progress_bar.pack(fill="x", pady=(0, 4))

        # First line of status (Main action & video time)
        status_line1 = ttk.Frame(status_frame)
        status_line1.pack(fill="x")

        self.status_label = ttk.Label(
            status_line1,
            text="待機中: 解析したい動画または画像を選択してください",
            font=("Segoe UI", 9, "bold"),
            foreground="#2C3E50",
        )
        self.status_label.pack(side="left")

        self.event_count_label = ttk.Label(
            status_line1,
            text="",
            font=("Segoe UI", 9, "bold"),
            foreground="#1F618D",
        )
        self.event_count_label.pack(side="right")

        # Second line of status (Real elapsed time & Estimated remaining time)
        status_line2 = ttk.Frame(status_frame)
        status_line2.pack(fill="x", pady=(2, 0))

        self.time_info_label = ttk.Label(
            status_line2,
            text="",
            font=("Segoe UI", 8),
            foreground="#666666",
        )
        self.time_info_label.pack(side="left")

        # 3. Bottom Action Bar (Packed first to bottom so it NEVER collapses!)
        action_frame = ttk.Frame(self.main_container)
        action_frame.pack(side="bottom", fill="x", pady=(4, 0))

        # Left action buttons
        self.btn_pause_resume = ttk.Button(
            action_frame,
            text="中断",
            command=self._toggle_pause,
            state="disabled",
        )
        self.btn_pause_resume.pack(side="left")

        self.btn_clear = ttk.Button(
            action_frame,
            text="クリア (初期化)",
            command=self._reset_to_initial_state,
        )
        self.btn_clear.pack(side="left", padx=(8, 0))

        # コピーボタンはオミット（コメントアウト）
        # self.btn_copy = ttk.Button(
        #     action_frame,
        #     text="コピー",
        #     command=self._copy_to_clipboard,
        #     state="disabled",
        # )
        # self.btn_copy.pack(side="left", padx=(8, 0))

        # Right action buttons: [ 別名で保存... ] [ 📁 保存フォルダを開く ]
        self.btn_save = ttk.Button(
            action_frame,
            text="別名で保存...",
            command=self._save_selected,
            state="disabled",
        )
        self.btn_save.pack(side="right")

        self.btn_open_folder = ttk.Button(
            action_frame,
            text="📁 保存フォルダを開く",
            command=self._open_output_folder,
            state="disabled",
            style="Primary.TButton",
        )
        self.btn_open_folder.pack(side="right", padx=(0, 8))

        # 3.5. Output Destination & Auto-Save Bar (Packed directly above action_frame)
        dest_frame = ttk.LabelFrame(
            self.main_container, text=" 自動保存先・出力設定 ", padding="6"
        )
        dest_frame.pack(side="bottom", fill="x", pady=(0, 6))

        dest_box = ttk.Frame(dest_frame)
        dest_box.pack(fill="x")

        ttk.Label(
            dest_box, text="保存先フォルダ:", font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 4))
        self.entry_dest_dir = ttk.Entry(
            dest_box, textvariable=self.dest_dir_var, font=("Segoe UI", 9)
        )
        self.entry_dest_dir.pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )

        self.btn_browse_dest = ttk.Button(
            dest_box, text="参照...", command=self._browse_dest_dir
        )
        self.btn_browse_dest.pack(side="left", padx=(0, 10))

        self.chk_save_json = ttk.Checkbutton(
            dest_box,
            text="JSON",
            variable=self.chk_save_json_var,
            command=self._on_save_settings_change,
        )
        self.chk_save_json.pack(side="left", padx=(0, 6))

        self.chk_save_preview = ttk.Checkbutton(
            dest_box,
            text="見せ合い画像",
            variable=self.chk_save_preview_var,
            command=self._on_save_settings_change,
        )
        self.chk_save_preview.pack(side="left")

        # 4. Middle-Bottom Section: Team Preview (6on6) Section (Packed above action_frame)
        thumb_frame = ttk.LabelFrame(self.main_container, text=" 選出見せ合い画面 (6on6) ", padding="8")
        thumb_frame.pack(side="bottom", fill="x", pady=(0, 8))

        thumb_box = ttk.Frame(thumb_frame)
        thumb_box.pack(fill="x")

        # Fixed size container (214x120 pixels, exactly 16:9) to keep height completely stable
        self.thumb_container = tk.Frame(thumb_box, width=214, height=120, bg="#23272D", relief="sunken", bd=1)
        self.thumb_container.pack_propagate(False)
        self.thumb_container.pack(side="left", padx=(0, 12))

        self.initial_thumb_text = "選出画面を検出すると\nここに画像が表示されます"
        self.thumb_label = tk.Label(
            self.thumb_container,
            text=self.initial_thumb_text,
            bg="#23272D",
            fg="#8B949E",
            font=("Segoe UI", 8),
            justify="center",
        )
        self.thumb_label.pack(fill="both", expand=True)

        info_box = ttk.Frame(thumb_box)
        info_box.pack(side="left", fill="both", expand=True)

        self.thumb_info_title = ttk.Label(
            info_box,
            text="6on6 選出見せ合い画面キャプチャ",
            font=("Segoe UI", 9, "bold"),
            foreground="#2C3E50",
        )
        self.thumb_info_title.pack(anchor="w", pady=(2, 4))

        self.thumb_info_desc = ttk.Label(
            info_box,
            text="動画序盤の選出画面を自動検出し、相手パーティ6体＋自分の持ち物を高画質記録します。\n「JSONを保存」実行時に、同じフォルダへ _preview.png として自動でペア保存されます。",
            font=("Segoe UI", 8),
            foreground="#555555",
            justify="left",
        )
        self.thumb_info_desc.pack(anchor="w")

        # 5. Middle Section: JSON Preview (Fills all remaining vertical space!)
        json_frame = ttk.LabelFrame(self.main_container, text=" 抽出 JSON プレビュー ", padding="10")
        json_frame.pack(side="top", fill="both", expand=True, pady=(0, 8))

        self.text_area = ScrolledText(
            json_frame,
            wrap="none",
            font=("Consolas", 10),
            bg="#1E1E1E",
            fg="#D4D4D4",
            insertbackground="#FFFFFF",
            selectbackground="#264F78",
            padx=8,
            pady=8,
        )
        self.text_area.pack(fill="both", expand=True)

    def _build_queue_panel(self):
        """Construct the collapsible batch processing queue side panel."""
        panel_header = ttk.Frame(self.queue_panel)
        panel_header.pack(fill="x", pady=(0, 6))

        self.queue_title_label = ttk.Label(
            panel_header,
            text="📋 処理キュー (0件)",
            font=("Segoe UI", 10, "bold"),
            foreground="#2C3E50",
        )
        self.queue_title_label.pack(side="left")

        btn_close_queue = ttk.Button(
            panel_header,
            text="✕",
            width=3,
            command=self._hide_queue_panel,
        )
        btn_close_queue.pack(side="right")

        # Action toolbar for queue
        queue_toolbar = ttk.Frame(self.queue_panel)
        queue_toolbar.pack(fill="x", pady=(0, 6))

        btn_clear_comp = ttk.Button(
            queue_toolbar,
            text="完了をクリア",
            command=self._on_queue_clear_completed,
        )
        btn_clear_comp.pack(side="left", padx=(0, 4))

        btn_clear_all = ttk.Button(
            queue_toolbar,
            text="すべてクリア",
            command=self._on_queue_clear_all,
        )
        btn_clear_all.pack(side="left")

        # Queue Treeview container
        tree_container = ttk.Frame(self.queue_panel)
        tree_container.pack(fill="both", expand=True)

        columns = ("idx", "name", "status")
        self.tree_queue = ttk.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree_queue.heading("idx", text="#")
        self.tree_queue.heading("name", text="ファイル名")
        self.tree_queue.heading("status", text="状態")

        self.tree_queue.column("idx", width=28, anchor="center")
        self.tree_queue.column("name", width=190, anchor="w")
        self.tree_queue.column("status", width=75, anchor="center")

        scrollbar_q = ttk.Scrollbar(
            tree_container, orient="vertical", command=self.tree_queue.yview
        )
        self.tree_queue.configure(yscrollcommand=scrollbar_q.set)

        self.tree_queue.pack(side="left", fill="both", expand=True)
        scrollbar_q.pack(side="right", fill="y")

        # Context Menu
        self.menu_queue = tk.Menu(self, tearoff=0)
        self.menu_queue.add_command(
            label="この項目を削除", command=self._on_queue_delete_selected
        )
        self.menu_queue.add_command(
            label="完了済みをクリア", command=self._on_queue_clear_completed
        )
        self.menu_queue.add_command(
            label="すべてクリア", command=self._on_queue_clear_all
        )

        self.tree_queue.bind("<Button-3>", self._on_queue_right_click)
        self.tree_queue.bind("<ButtonPress-1>", self._on_tree_drag_start)
        self.tree_queue.bind("<B1-Motion>", self._on_tree_drag_motion)
        self.tree_queue.bind("<ButtonRelease-1>", self._on_tree_drag_release)
        self.tree_queue.bind("<<TreeviewSelect>>", self._on_queue_item_select)

        # Help hint label
        hint_label = ttk.Label(
            self.queue_panel,
            text="💡 ドラッグで順番変更 / 右クリックで削除",
            font=("Segoe UI", 8),
            foreground="#888888",
        )
        hint_label.pack(fill="x", pady=(4, 0))

    def _toggle_queue_panel(self):
        """Toggle queue panel visibility."""
        if self._is_queue_open:
            self._hide_queue_panel()
        else:
            self._show_queue_panel()

    def _show_queue_panel(self):
        """Expand the window and display the queue panel."""
        if not self._is_queue_open:
            self._is_queue_open = True
            self.queue_panel.pack(side="right", fill="both", padx=(4, 0))
            cur_w = self.winfo_width()
            cur_h = self.winfo_height()
            self.minsize(980, 560)
            if cur_w < 1120:
                self.geometry(f"1120x{max(cur_h, 760)}")
        self._update_queue_ui()

    def _hide_queue_panel(self):
        """Collapse the queue panel and restore compact window width."""
        if self._is_queue_open:
            self._is_queue_open = False
            self.queue_panel.pack_forget()
            cur_w = self.winfo_width()
            cur_h = self.winfo_height()
            self.minsize(680, 560)
            if cur_w > 820:
                self.geometry(f"820x{max(cur_h, 760)}")
        self._update_queue_ui()

    def _update_queue_ui(self):
        """Refresh queue button counter, title, and Treeview rows."""
        total = self.queue_mgr.total_count
        comp = self.queue_mgr.completed_count
        btn_text = f"📋 キュー ({total}件)" if total > 0 else "📋 キュー"
        if self._is_queue_open:
            btn_text += " ▲"
        self.btn_toggle_queue.config(text=btn_text)
        self.queue_title_label.config(text=f"📋 処理キュー ({comp}/{total} 完了)")

        # Re-populate Treeview
        for row in self.tree_queue.get_children():
            self.tree_queue.delete(row)

        for idx, item in enumerate(self.queue_mgr.items, start=1):
            self.tree_queue.insert(
                "",
                "end",
                iid=item.item_id,
                values=(idx, item.display_name, item.status.label),
            )
            if item.status == QueueStatus.PROCESSING:
                self.tree_queue.selection_set(item.item_id)

    def _on_queue_right_click(self, event):
        row_id = self.tree_queue.identify_row(event.y)
        if row_id:
            self.tree_queue.selection_set(row_id)
        self.menu_queue.post(event.x_root, event.y_root)

    def _on_tree_drag_start(self, event):
        row_id = self.tree_queue.identify_row(event.y)
        if row_id:
            idx = self.tree_queue.index(row_id)
            self._drag_data = {"item_id": row_id, "index": idx}
        else:
            self._drag_data = {"item_id": None, "index": None}

    def _on_tree_drag_motion(self, event):
        target_row = self.tree_queue.identify_row(event.y)
        if target_row and target_row != self._drag_data.get("item_id"):
            self.tree_queue.selection_set(target_row)

    def _on_tree_drag_release(self, event):
        from_idx = self._drag_data.get("index")
        if from_idx is not None:
            target_row = self.tree_queue.identify_row(event.y)
            if target_row:
                to_idx = self.tree_queue.index(target_row)
                if from_idx != to_idx:
                    self.queue_mgr.move_item(from_idx, to_idx)
                    self._update_queue_ui()
                    items = self.tree_queue.get_children()
                    if 0 <= to_idx < len(items):
                        self.tree_queue.selection_set(items[to_idx])
        self._drag_data = {"item_id": None, "index": None}

    def _on_queue_item_select(self, event):
        selected = self.tree_queue.selection()
        if not selected:
            return
        row_id = selected[0]
        item = self.queue_mgr.get_by_id(row_id)
        if item and item.status == QueueStatus.COMPLETED and not self._is_processing:
            if item.json_result:
                self.current_json = item.json_result
                self.default_filename = item.default_filename
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert(tk.END, item.json_result)
                self._set_preview_image(item.preview_frame)
                opp = (
                    item.battle_data.get("opponent", "相手")
                    if item.battle_data
                    else "相手"
                )
                cnt = (
                    item.battle_data.get("events_count", 0)
                    if item.battle_data
                    else 0
                )
                self.status_label.config(
                    text=f"✓ 解析結果: {item.display_name} (対戦相手: {opp})"
                )
                self.event_count_label.config(text=f"検出イベント数: {cnt} 件")
                self.btn_save.config(state="normal")
                self.btn_open_folder.config(state="normal")

    def _on_queue_delete_selected(self):
        selected = self.tree_queue.selection()
        if not selected:
            return
        item_id = selected[0]
        item = self.queue_mgr.get_by_id(item_id)
        if item and item.status == QueueStatus.PROCESSING:
            messagebox.showwarning(
                "削除不可", "現在解析中のアイテムは削除できません。中断してください。"
            )
            return
        self.queue_mgr.remove_by_id(item_id)
        self._update_queue_ui()

    def _on_queue_clear_completed(self):
        self.queue_mgr.clear_completed()
        self._update_queue_ui()

    def _on_queue_clear_all(self):
        self.queue_mgr.clear_all()
        self._update_queue_ui()

    def _on_drop(self, event):
        raw_data = event.data
        paths = []
        if raw_data.startswith("{") and raw_data.endswith("}"):
            tokens = raw_data.replace("} {", "\n").replace("{", "").replace("}", "").split("\n")
            paths = [t.strip() for t in tokens if t.strip()]
        else:
            paths = [p.strip() for p in raw_data.split() if p.strip()]

        if not paths:
            return

        video_exts = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        image_exts = [".png", ".jpg", ".jpeg", ".bmp", ".webp"]

        video_files = [p for p in paths if Path(p).suffix.lower() in video_exts]
        image_files = [p for p in paths if Path(p).suffix.lower() in image_exts]

        if video_files:
            if len(video_files) == 1 and not self._is_processing and self.queue_mgr.total_count == 0:
                # Single video processing (direct)
                self._start_video_processing(video_files[0])
            else:
                # Multiple videos or queuing to existing workload
                self.queue_mgr.add_files(video_files)
                self._batch_session_total = max(self._batch_session_total, self.queue_mgr.total_count)
                self._show_queue_panel()
                if not self._is_processing:
                    self._process_next_queue_item()
        elif image_files:
            if not self._is_processing and self.queue_mgr.total_count == 0:
                self._start_images_processing(sorted(image_files))
            else:
                messagebox.showinfo("キュー対応", "バッチキューは動画ファイルを対象としています。")
        else:
            first_p = paths[0]
            messagebox.showwarning(
                "非対応ファイル",
                f"対応している動画または画像形式を選択してください。\n対象: {Path(first_p).name}",
            )

    def _browse_video(self):
        file_paths = filedialog.askopenfilenames(
            title="対戦動画を選択（複数可）",
            filetypes=[
                ("動画ファイル", "*.mp4 *.mov *.avi *.mkv *.webm"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not file_paths:
            return

        files = list(file_paths)
        if len(files) == 1 and not self._is_processing and self.queue_mgr.total_count == 0:
            self._start_video_processing(files[0])
        else:
            self.queue_mgr.add_files(files)
            self._batch_session_total = max(self._batch_session_total, self.queue_mgr.total_count)
            self._show_queue_panel()
            if not self._is_processing:
                self._process_next_queue_item()

    def _browse_images(self):
        if self._is_processing:
            return
        files = filedialog.askopenfilenames(
            title="スクショ画像群を選択（複数可）",
            filetypes=[
                ("画像ファイル", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if files:
            self._start_images_processing(sorted(list(files)))

    def _on_save_settings_change(self):
        """Persist output destination and format settings to config."""
        save_app_settings(
            {
                "output_dir": self.dest_dir_var.get().strip(),
                "save_json": bool(self.chk_save_json_var.get()),
                "save_preview": bool(self.chk_save_preview_var.get()),
            }
        )

    def _browse_dest_dir(self):
        """Open directory picker dialog to select default output folder."""
        initial = self.dest_dir_var.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(
            title="保存先フォルダを選択",
            initialdir=initial if Path(initial).exists() else str(Path.home()),
        )
        if chosen:
            self.dest_dir_var.set(chosen)
            self._on_save_settings_change()

    def _open_output_folder(self):
        """Open the target output folder in file explorer."""
        target_dir = self.dest_dir_var.get().strip() or self.last_saved_output_dir
        if not target_dir or not Path(target_dir).exists():
            target_dir = str(Path.home())
        try:
            if sys.platform == "win32":
                os.startfile(target_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", target_dir])
            else:
                subprocess.run(["xdg-open", target_dir])
        except Exception as e:
            messagebox.showerror("フォルダ表示エラー", f"フォルダを開けませんでした:\n{e}")

    def _auto_save_result(
        self,
        source_path: str,
        default_filename: str,
        json_str: str,
        preview_frame: Optional[np.ndarray],
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Automatically save JSON and/or 6on6 preview image to destination folder."""
        dest_dir_str = self.dest_dir_var.get().strip()
        if dest_dir_str:
            dest_dir = Path(dest_dir_str)
        else:
            # Default to the parent folder of the input video
            dest_dir = Path(source_path).parent

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            self.last_saved_output_dir = str(dest_dir)
        except Exception:
            dest_dir = Path.home()
            dest_dir.mkdir(parents=True, exist_ok=True)
            self.last_saved_output_dir = str(dest_dir)

        saved_json_path = None
        saved_preview_path = None

        # Auto-save JSON
        if self.chk_save_json_var.get() and json_str:
            try:
                json_path = dest_dir / default_filename
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                saved_json_path = json_path
            except Exception:
                pass

        # Auto-save Preview Image
        if self.chk_save_preview_var.get() and preview_frame is not None:
            try:
                from poke_saifu.core import save_image_unicode

                img_stem = Path(default_filename).stem
                img_path = dest_dir / f"{img_stem}_preview.png"
                if save_image_unicode(img_path, preview_frame):
                    saved_preview_path = img_path
            except Exception:
                pass

        return saved_json_path, saved_preview_path

    def _set_ui_state(self, processing: bool):
        self._is_processing = processing
        state = "disabled" if processing else "normal"

        # Lock down inputs and configuration options during processing
        self.btn_browse_video.config(state=state)
        self.btn_browse_images.config(state=state)
        self.btn_toggle_queue.config(state=state)
        self.entry_dest_dir.config(state=state)
        self.btn_browse_dest.config(state=state)
        self.chk_save_json.config(state=state)
        self.chk_save_preview.config(state=state)
        self.btn_clear.config(state=state)

        if processing:
            # ONLY Pause/Resume is enabled while processing!
            self.btn_pause_resume.config(state="normal", text="中断")
            self.btn_save.config(state="disabled")
            self.btn_open_folder.config(state="disabled")
        else:
            self.btn_pause_resume.config(state="disabled", text="中断")
            self._is_paused = False
            if self.current_json:
                self.btn_save.config(state="normal")
                self.btn_open_folder.config(state="normal")
            else:
                self.btn_save.config(state="disabled")
                self.btn_open_folder.config(state="disabled")

    def _toggle_pause(self):
        """Toggle pause / resume of the parsing process."""
        if not self._is_processing:
            return

        if not self._is_paused:
            # Enter paused state
            self._pause_event.clear()
            self._is_paused = True
            self.taskbar.set_paused(self._get_root_hwnd())
            self.btn_pause_resume.config(text="再開")
            self.status_label.config(text="一時中断中 (処理を一時停止しています)")
            self.time_info_label.config(text="[再開] を押すと続きから解析を再開します。[クリア] で初期状態に戻せます。")
        else:
            # Resume processing
            self._pause_event.set()
            self._is_paused = False
            self.taskbar.set_resumed(self._get_root_hwnd())
            self.btn_pause_resume.config(text="中断")
            self.status_label.config(text="解析を再開しました...")

    def _reset_to_initial_state(self):
        """Completely reset the UI and cancel any ongoing process back to startup state."""
        # Invalidate current session and signal all running threads to terminate
        self._current_session_id += 1
        self._cancel_event.set()
        self._pause_event.set()

        self._is_processing = False
        self._is_paused = False
        self._current_queue_item = None
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        self.queue_mgr.clear_all()
        self._update_queue_ui()

        # Reset UI elements to fresh startup state
        self.drop_label.config(text=self.initial_dnd_text, bg="#EBF3FA")
        self.status_label.config(text="待機中: 解析したい動画または画像を選択してください")
        self.time_info_label.config(text="")
        self.event_count_label.config(text="")
        self.progress_bar["value"] = 0
        self.taskbar.clear(self._get_root_hwnd())

        self.current_json = ""
        self._set_preview_image(None)
        self.text_area.delete("1.0", tk.END)

        self.btn_browse_video.config(state="normal")
        self.btn_browse_images.config(state="normal")
        self.btn_toggle_queue.config(state="normal")
        self.entry_dest_dir.config(state="normal")
        self.btn_browse_dest.config(state="normal")
        self.chk_save_json.config(state="normal")
        self.chk_save_preview.config(state="normal")
        self.btn_pause_resume.config(state="disabled", text="中断")
        self.btn_save.config(state="disabled")
        self.btn_open_folder.config(state="disabled")

    def _set_preview_image(self, frame_bgr: Optional[np.ndarray]):
        """Update the 16:9 team preview thumbnail widget."""
        self.current_preview_frame = frame_bgr
        if frame_bgr is None:
            self.thumb_label.config(image="", text=self.initial_thumb_text)
            self.thumb_label.image = None
            self._preview_photo_image = None
            self.thumb_info_title.config(text="6on6 選出見せ合い画面キャプチャ", foreground="#2C3E50")
            return

        try:
            import cv2
            from PIL import Image, ImageTk

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)

            # Fixed 16:9 resolution fitting container (214x120)
            target_w = 214
            target_h = 120
            resized_pil = pil_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            self._preview_photo_image = ImageTk.PhotoImage(resized_pil)
            self.thumb_label.config(image=self._preview_photo_image, text="")
            self.thumb_label.image = self._preview_photo_image
            self.thumb_info_title.config(text="✓ 6on6 選出見せ合い画面を検出しました！", foreground="#27AE60")
        except Exception:
            pass

    def _process_next_queue_item(self):
        """Pick the next waiting item in the queue and start processing."""
        next_item = self.queue_mgr.get_next_waiting()
        if not next_item:
            # All items in queue have finished!
            self._current_queue_item = None
            self._set_ui_state(False)
            self._update_queue_ui()

            # Trigger batch completion alerts if batch had items
            if self._batch_session_total > 0:
                self.taskbar.flash(self._get_root_hwnd())
                if self.sound_enabled_var.get():
                    play_completion_sound()
                if self.toast_enabled_var.get():
                    toast_msg = build_completion_toast_message(
                        opponent=self._batch_last_opponent or "相手",
                        count=self._batch_last_events_count,
                        total_items=self._batch_session_total,
                    )
                    show_toast_notification(title="Poke-Saifu", message=toast_msg)
                self._batch_session_total = 0
            return

        next_item.status = QueueStatus.PROCESSING
        self._current_queue_item = next_item
        self._update_queue_ui()
        self._start_video_processing(next_item.file_path, is_queue_run=True)

    def _start_video_processing(self, video_path: str, is_queue_run: bool = False):
        # Terminate any existing sessions
        self._current_session_id += 1
        session_id = self._current_session_id

        self._cancel_event.set()
        self._cancel_event = threading.Event()
        self._pause_event.set()
        self._is_paused = False

        cancel_ev = self._cancel_event
        pause_ev = self._pause_event

        self._set_ui_state(True)
        self._set_preview_image(None)
        display_name = Path(video_path).name
        self.drop_label.config(text=f"選択中: {display_name}")
        self.status_label.config(text="解析の準備中... (OCRエンジン初期化)")
        self.event_count_label.config(text="")
        self.time_info_label.config(text="")
        self.progress_bar["value"] = 0
        self.taskbar.set_indeterminate(self._get_root_hwnd())
        self.text_area.delete("1.0", tk.END)

        def thread_target():
            def on_progress(val: float, info: Any):
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(0, lambda: self._update_progress(val, info, session_id))

            try:
                json_str, default_name, battle_data, preview_frame = self.parser.process_video(
                    video_path,
                    progress_callback=on_progress,
                    cancel_event=cancel_ev,
                    pause_event=pause_ev,
                )
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(
                        0,
                        lambda: self._on_success(
                            json_str,
                            default_name,
                            battle_data,
                            preview_frame,
                            session_id,
                            source_path=video_path,
                            is_queue_run=is_queue_run,
                        ),
                    )
            except Exception as e:
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(
                        0,
                        lambda: self._on_error(
                            str(e), session_id, is_queue_run=is_queue_run
                        ),
                    )

        threading.Thread(target=thread_target, daemon=True).start()

    def _start_images_processing(self, image_paths: List[str]):
        self._current_session_id += 1
        session_id = self._current_session_id

        self._cancel_event.set()
        self._cancel_event = threading.Event()
        self._pause_event.set()
        self._is_paused = False

        cancel_ev = self._cancel_event
        pause_ev = self._pause_event

        self._set_ui_state(True)
        self._set_preview_image(None)
        self.drop_label.config(text=f"選択中: 画像 {len(image_paths)} 枚")
        self.status_label.config(text="画像群の解析準備中...")
        self.event_count_label.config(text="")
        self.time_info_label.config(text="")
        self.progress_bar["value"] = 0
        self.taskbar.set_indeterminate(self._get_root_hwnd())
        self.text_area.delete("1.0", tk.END)

        def thread_target():
            def on_progress(val: float, info: Any):
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(0, lambda: self._update_progress(val, info, session_id))

            try:
                json_str, default_name, battle_data, preview_frame = self.parser.process_images(
                    image_paths,
                    progress_callback=on_progress,
                    cancel_event=cancel_ev,
                    pause_event=pause_ev,
                )
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    img_src = image_paths[0] if image_paths else ""
                    self.after(
                        0,
                        lambda: self._on_success(
                            json_str,
                            default_name,
                            battle_data,
                            preview_frame,
                            session_id,
                            source_path=img_src,
                            is_queue_run=False,
                        ),
                    )
            except Exception as e:
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(
                        0,
                        lambda: self._on_error(
                            str(e), session_id, is_queue_run=False
                        ),
                    )

        threading.Thread(target=thread_target, daemon=True).start()

    def _update_progress(self, val: float, info: Any, session_id: int):
        if session_id != self._current_session_id or self._is_paused or self._cancel_event.is_set():
            return

        self.progress_bar["value"] = val * 100
        self.taskbar.set_progress(self._get_root_hwnd(), val, paused=self._is_paused)
        if isinstance(info, dict):
            preview_f = info.get("preview_frame")
            if preview_f is not None and self.current_preview_frame is None:
                self._set_preview_image(preview_f)

            video_time = info.get("video_time_str", "00:00")
            video_dur = info.get("video_duration_str", "00:00")
            elapsed = info.get("elapsed_str", "00:00")
            eta = info.get("eta_str", "--:--")
            events_cnt = info.get("events_count", 0)

            queue_prefix = ""
            if self._current_queue_item and self.queue_mgr.total_count > 1:
                comp = self.queue_mgr.completed_count
                total = self.queue_mgr.total_count
                queue_prefix = f"[{comp + 1}/{total}] "

            self.status_label.config(
                text=f"{queue_prefix}解析中: 動画再生位置 {video_time} / {video_dur} ({int(val * 100)}%)"
            )
            self.time_info_label.config(
                text=f"⏱️ 処理時間: {elapsed}   |   ⏳ 推定残り時間: 約 {eta}"
            )
            self.event_count_label.config(
                text=f"検出イベント: {events_cnt} 件"
            )
        else:
            self.status_label.config(text=str(info))

    def _on_notification_setting_change(self):
        """Persist updated notification settings to user config."""
        save_notification_settings(
            sound_enabled=self.sound_enabled_var.get(),
            toast_enabled=self.toast_enabled_var.get(),
        )

    def _on_success(
        self,
        json_str: str,
        default_name: str,
        battle_data: dict,
        preview_frame: Optional[np.ndarray],
        session_id: int,
        source_path: str = "",
        is_queue_run: bool = False,
    ):
        if session_id != self._current_session_id:
            return

        self._set_ui_state(False)
        self.current_json = json_str
        self.default_filename = default_name
        self._set_preview_image(preview_frame)

        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, json_str)

        events_count = battle_data.get("events_count", 0)
        opponent = battle_data.get("opponent", "opponent")
        was_interrupted = battle_data.get("interrupted", False)
        has_preview = battle_data.get("has_preview_image", False)

        preview_note = " (選出画面検出あり)" if has_preview else ""

        # Auto-save files if not interrupted
        saved_note = ""
        if not was_interrupted:
            actual_source = source_path
            if not actual_source and self._current_queue_item:
                actual_source = self._current_queue_item.file_path
            saved_j, saved_p = self._auto_save_result(
                source_path=actual_source,
                default_filename=default_name,
                json_str=json_str,
                preview_frame=preview_frame,
            )
            saved_items = []
            if saved_j:
                saved_items.append("JSON")
            if saved_p:
                saved_items.append("画像")
            if saved_items:
                saved_note = f" [自動保存: {'+'.join(saved_items)}]"

        if was_interrupted:
            self.status_label.config(
                text=f"⏹️ 中断された時点までの結果を表示しています (対戦相手: {opponent}){preview_note}"
            )
            self.time_info_label.config(
                text="処理は中断されました。下部のボタンから別名保存またはフォルダ確認が可能です。"
            )
        else:
            self.status_label.config(
                text=f"✓ 解析完了！ (対戦相手: {opponent}){preview_note}{saved_note}"
            )
            self.time_info_label.config(
                text=f"解析が完了し、指定フォルダへ自動保存されました。 (保存先: {self.last_saved_output_dir or '動画フォルダ'})"
            )

        self.event_count_label.config(text=f"検出イベント数: {events_count} 件")
        self.progress_bar["value"] = 100
        self.taskbar.clear(self._get_root_hwnd())

        self.btn_save.config(state="normal")
        self.btn_open_folder.config(state="normal")

        # Update queue item data if this was a queued run
        if self._current_queue_item:
            self._current_queue_item.status = (
                QueueStatus.CANCELLED if was_interrupted else QueueStatus.COMPLETED
            )
            self._current_queue_item.json_result = json_str
            self._current_queue_item.default_filename = default_name
            self._current_queue_item.battle_data = battle_data
            self._current_queue_item.preview_frame = preview_frame
            self._batch_last_opponent = opponent
            self._batch_last_events_count = events_count
            self._update_queue_ui()

        if is_queue_run:
            # Continue to next item in the queue if not interrupted
            if not was_interrupted:
                self.after(200, self._process_next_queue_item)
        else:
            # Standalone single item alerts
            if not was_interrupted:
                self.taskbar.flash(self._get_root_hwnd())
                if self.sound_enabled_var.get():
                    play_completion_sound()
                if self.toast_enabled_var.get():
                    toast_msg = build_completion_toast_message(
                        opponent=opponent,
                        count=events_count,
                        total_items=1,
                    )
                    show_toast_notification(title="Poke-Saifu", message=toast_msg)

    def _on_error(self, err_msg: str, session_id: int, is_queue_run: bool = False):
        if session_id != self._current_session_id:
            return

        self._set_ui_state(False)
        self.status_label.config(text="エラーが発生しました")
        self.time_info_label.config(text="")
        self.progress_bar["value"] = 0
        self.taskbar.set_error(self._get_root_hwnd())

        if self._current_queue_item:
            self._current_queue_item.status = QueueStatus.ERROR
            self._current_queue_item.error_message = err_msg
            self._update_queue_ui()

        if is_queue_run:
            # Continue with remaining items in queue
            self.after(500, self._process_next_queue_item)
        else:
            messagebox.showerror("解析エラー", f"処理中にエラーが発生しました:\n\n{err_msg}")

    # def _copy_to_clipboard(self):
    #     """Copy current JSON to clipboard (omitted)."""
    #     if not self.current_json:
    #         return
    #     self.clipboard_clear()
    #     self.clipboard_append(self.current_json)
    #     messagebox.showinfo("コピー完了", "JSONテキストをクリップボードにコピーしました！")

    def _save_selected(self):
        """Save selected outputs (JSON and/or 6on6 Team Preview image)."""
        save_json = self.chk_save_json_var.get()
        save_preview = self.chk_save_preview_var.get()

        if not save_json and not save_preview:
            messagebox.showwarning(
                "保存対象の選択",
                "保存する対象（「見せ合い画像」または「JSON」）にチェックを入れてください。",
            )
            return

        content = self.text_area.get("1.0", tk.END).strip()

        # Case 1: Saving JSON (with or without preview image)
        if save_json:
            if not content:
                messagebox.showwarning("データなし", "保存するJSONデータがありません。")
                return

            file_path = filedialog.asksaveasfilename(
                title="解析結果JSONを保存",
                initialfile=self.default_filename,
                defaultextension=".json",
                filetypes=[("JSON ファイル", "*.json"), ("すべてのファイル", "*.*")],
            )
            if not file_path:
                return

            saved_files = []
            try:
                # Save JSON with UTF-8
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                saved_files.append(f"📄 {Path(file_path).name}")

                # Save 6on6 preview image with Unicode-safe saver if available & checked
                if save_preview and self.current_preview_frame is not None:
                    from poke_saifu.core import save_image_unicode

                    img_path = Path(file_path).with_name(f"{Path(file_path).stem}_preview.png")
                    save_image_unicode(img_path, self.current_preview_frame)
                    saved_files.append(f"🖼️ {img_path.name}")

                msg = "ファイルを保存しました:\n\n" + "\n".join(saved_files)
                messagebox.showinfo("保存成功", msg)
            except Exception as e:
                messagebox.showerror("保存エラー", f"ファイルの保存に失敗しました:\n{e}")

        # Case 2: Saving Preview image only
        else:
            if self.current_preview_frame is None:
                messagebox.showwarning("画像なし", "保存する見せ合い画像がありません。")
                return

            base_name = Path(self.default_filename).stem
            default_img_name = f"{base_name}_preview.png"

            file_path = filedialog.asksaveasfilename(
                title="見せ合い画像の保存先を選択",
                initialfile=default_img_name,
                defaultextension=".png",
                filetypes=[
                    ("PNG画像", "*.png"),
                    ("JPEG画像", "*.jpg"),
                    ("すべてのファイル", "*.*"),
                ],
            )
            if not file_path:
                return

            try:
                from poke_saifu.core import save_image_unicode

                save_image_unicode(file_path, self.current_preview_frame)
                messagebox.showinfo("保存完了", f"見せ合い画像を保存しました:\n\n🖼️ {Path(file_path).name}")
            except Exception as e:
                messagebox.showerror("保存エラー", f"画像の保存に失敗しました:\n{e}")
