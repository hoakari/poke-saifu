"""GUI application for Poke-Saifu.

Provides Drag & Drop file input, processing progress feedback,
JSON preview with copy action, and customized save dialog.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, List, Optional
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

from poke_saifu.parser import BattleParser
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
        self.current_json: str = ""
        self.current_preview_frame: Optional[np.ndarray] = None
        self._preview_photo_image: Any = None
        self.default_filename: str = f"{datetime.now().strftime('%Y-%m-%d')}_vs_opponent.json"
        self._is_processing: bool = False
        self._is_paused: bool = False
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

        self.configure(bg="#F4F6F9")

    def _build_ui(self):
        # Container with padding
        main_container = ttk.Frame(self, padding="15 15 15 15")
        main_container.pack(fill="both", expand=True)

        # 1. Top Section: Drop Zone & Browse Buttons
        drop_frame = ttk.LabelFrame(main_container, text=" 解析対象の選択 (動画 / スクショ画像) ", padding="10")
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
        self.btn_browse_images.pack(fill="x")

        # 2. Middle Section: Progress & Status
        status_frame = ttk.Frame(main_container)
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
        action_frame = ttk.Frame(main_container)
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

        self.btn_copy = ttk.Button(
            action_frame,
            text="コピー",
            command=self._copy_to_clipboard,
            state="disabled",
        )
        self.btn_copy.pack(side="left", padx=(8, 0))

        # Right action buttons: [☑ 見せ合い画像] [☑ JSON] [ 保存... ]
        self.btn_save = ttk.Button(
            action_frame,
            text="保存...",
            command=self._save_selected,
            state="disabled",
            style="Primary.TButton",
        )
        self.btn_save.pack(side="right")

        self.chk_save_json_var = tk.BooleanVar(value=True)
        self.chk_save_preview_var = tk.BooleanVar(value=True)

        self.chk_save_json = ttk.Checkbutton(
            action_frame,
            text="JSON",
            variable=self.chk_save_json_var,
        )
        self.chk_save_json.pack(side="right", padx=(0, 10))

        self.chk_save_preview = ttk.Checkbutton(
            action_frame,
            text="見せ合い画像",
            variable=self.chk_save_preview_var,
        )
        self.chk_save_preview.pack(side="right", padx=(0, 6))

        # 4. Middle-Bottom Section: Team Preview (6on6) Section (Packed above action_frame)
        thumb_frame = ttk.LabelFrame(main_container, text=" 選出見せ合い画面 (6on6) ", padding="8")
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
        json_frame = ttk.LabelFrame(main_container, text=" 抽出 JSON プレビュー ", padding="10")
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

    def _on_drop(self, event):
        if self._is_processing:
            return

        raw_data = event.data
        paths = []
        if raw_data.startswith("{") and raw_data.endswith("}"):
            tokens = raw_data.replace("} {", "\n").replace("{", "").replace("}", "").split("\n")
            paths = [t.strip() for t in tokens if t.strip()]
        else:
            paths = [p.strip() for p in raw_data.split() if p.strip()]

        if not paths:
            return

        first_path = paths[0]
        ext = Path(first_path).suffix.lower()
        if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
            self._start_video_processing(first_path)
        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
            valid_imgs = [p for p in paths if Path(p).suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]]
            if valid_imgs:
                self._start_images_processing(sorted(valid_imgs))
        else:
            messagebox.showwarning("非対応ファイル", f"対応している動画または画像形式を選択してください。\n対象: {Path(first_path).name}")

    def _browse_video(self):
        if self._is_processing:
            return
        file_path = filedialog.askopenfilename(
            title="対戦動画を選択",
            filetypes=[
                ("動画ファイル", "*.mp4 *.mov *.avi *.mkv *.webm"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if file_path:
            self._start_video_processing(file_path)

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

    def _set_ui_state(self, processing: bool):
        self._is_processing = processing
        state = "disabled" if processing else "normal"
        self.btn_browse_video.config(state=state)
        self.btn_browse_images.config(state=state)

        if processing:
            self.btn_pause_resume.config(state="normal", text="中断")
            self.btn_save.config(state="disabled")
            self.btn_copy.config(state="disabled")
        else:
            self.btn_pause_resume.config(state="disabled", text="中断")
            self._is_paused = False

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
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

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
        self.btn_pause_resume.config(state="disabled", text="中断")
        self.btn_save.config(state="disabled")
        self.btn_copy.config(state="disabled")
        self.chk_save_json_var.set(True)
        self.chk_save_preview_var.set(True)

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

    def _start_video_processing(self, video_path: str):
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
        self.drop_label.config(text=f"選択中: {Path(video_path).name}")
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
                    self.after(0, lambda: self._on_success(json_str, default_name, battle_data, preview_frame, session_id))
            except Exception as e:
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(0, lambda: self._on_error(str(e), session_id))

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
                    self.after(0, lambda: self._on_success(json_str, default_name, battle_data, preview_frame, session_id))
            except Exception as e:
                if session_id == self._current_session_id and not cancel_ev.is_set():
                    self.after(0, lambda: self._on_error(str(e), session_id))

        threading.Thread(target=thread_target, daemon=True).start()

    def _update_progress(self, val: float, info: Any, session_id: int):
        if session_id != self._current_session_id or self._is_paused or self._cancel_event.is_set():
            return

        self.progress_bar["value"] = val * 100
        self.taskbar.set_progress(self._get_root_hwnd(), val, paused=self._is_paused)
        if isinstance(info, dict):
            # Real-time preview thumbnail update as soon as detected in video!
            preview_f = info.get("preview_frame")
            if preview_f is not None and self.current_preview_frame is None:
                self._set_preview_image(preview_f)

            video_time = info.get("video_time_str", "00:00")
            video_dur = info.get("video_duration_str", "00:00")
            elapsed = info.get("elapsed_str", "00:00")
            eta = info.get("eta_str", "--:--")
            events_cnt = info.get("events_count", 0)

            self.status_label.config(
                text=f"解析中: 動画再生位置 {video_time} / {video_dur} ({int(val * 100)}%)"
            )
            self.time_info_label.config(
                text=f"⏱️ 処理時間: {elapsed}   |   ⏳ 推定残り時間: 約 {eta}"
            )
            self.event_count_label.config(
                text=f"検出イベント: {events_cnt} 件"
            )
        else:
            self.status_label.config(text=str(info))

    def _on_success(
        self,
        json_str: str,
        default_name: str,
        battle_data: dict,
        preview_frame: Optional[np.ndarray],
        session_id: int,
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
        if was_interrupted:
            self.status_label.config(text=f"⏹️ 中断された時点までの結果を表示しています (対戦相手: {opponent}){preview_note}")
            self.time_info_label.config(text="処理は中断されました。保存またはコピーが可能です。")
        else:
            self.status_label.config(text=f"✓ 解析完了！ (対戦相手: {opponent}){preview_note}")
            self.time_info_label.config(text="解析が正常に終了しました。右下のボタンから保存またはコピーできます。")

        self.event_count_label.config(text=f"検出イベント数: {events_count} 件")
        self.progress_bar["value"] = 100
        self.taskbar.clear(self._get_root_hwnd())

        self.btn_save.config(state="normal")
        self.btn_copy.config(state="normal")

    def _on_error(self, err_msg: str, session_id: int):
        if session_id != self._current_session_id:
            return

        self._set_ui_state(False)
        self.status_label.config(text="エラーが発生しました")
        self.time_info_label.config(text="")
        self.progress_bar["value"] = 0
        self.taskbar.set_error(self._get_root_hwnd())
        messagebox.showerror("解析エラー", f"処理中にエラーが発生しました:\n\n{err_msg}")

    def _copy_to_clipboard(self):
        if not self.current_json:
            return
        self.clipboard_clear()
        self.clipboard_append(self.current_json)
        messagebox.showinfo("コピー完了", "JSONテキストをクリップボードにコピーしました！")

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
                title="保存先を選択",
                initialfile=self.default_filename,
                defaultextension=".json",
                filetypes=[("JSON ファイル", "*.json"), ("すべてのファイル", "*.*")],
            )
            if not file_path:
                return

            saved_files = []
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                saved_files.append(f"📄 {Path(file_path).name}")

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
