"""Battle video and image parser pipeline for Poke-Saifu.

Handles frame sampling, 6on6 team preview detection, text deduplication, and JSON export.
"""

from datetime import datetime
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from poke_saifu.core import (
    DEFAULT_ROI_MAIN,
    DEFAULT_ROI_POPUP_LEFT,
    DEFAULT_ROI_POPUP_RIGHT,
    DEFAULT_ROI_PREVIEW_CENTER,
    DEFAULT_ROI_PREVIEW_OPPONENT,
    OCRProcessor,
    crop_by_ratio,
    is_likely_text_mask,
    preprocess_and_remove_ruby,
    read_image_unicode,
    save_image_unicode,
)

SAMPLE_INTERVAL_SEC: float = 0.8


def format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    total_sec = max(0, int(seconds))
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{mins:02d}:{secs:02d}"


def string_similarity(a: str, b: str) -> float:
    """Calculate string similarity ratio between 0.0 and 1.0."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def clean_battle_text(raw_text: str, confidence: float, side: str) -> Optional[str]:
    """Clean and normalize OCR battle text using purely generic, Pokemon-specific rules."""
    if not raw_text or not raw_text.strip():
        return None

    # 1. Base confidence filtering
    if confidence < 0.25:
        return None

    text = raw_text.strip()

    # 2. Filter out Nintendo Switch UI / Notifications
    if any(kw in text for kw in ["Friend Streak", "reached a", "Congratulate", "Friend", "Streak", "reacheda"]):
        return None

    # 3. Filter out battle command selection UI / timers
    if any(kw in text for kw in ["様子を見る", "技の説明", "つよさの表示"]):
        return None
    if re.match(r"^\d+\s+\d{2}\s+(?:oo|\d{2})$", text):
        return None

    # 4. Filter out meaningless single symbols or fragmented noise
    cleaned_symbols = re.sub(r"[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", "", text)
    if len(cleaned_symbols) <= 1 and confidence < 0.8:
        return None
    if len(cleaned_symbols) <= 2 and confidence < 0.55:
        return None

    # Discard fragmented noise that lacks any coherent Japanese word
    if not re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]{2,}", text):
        return None

    # 5. Clean common OCR misrecognitions
    text = re.sub(r"^[ノ/‥\.\-_~^@\s,;:'\"|!]+", "", text)
    text = re.sub(r"[\s,;:'\"|~^@]+$", "", text)

    # Strip single garbage prefixes before key phrases (e.g. 'い 相手の', 'r 相手の')
    text = re.sub(r"^(?:[a-zA-Z0-9ぁ-んァ-ヶ]\s+)+(?=相手の|あいての|ゆけっ|効果は|しかし|勝負に)", "", text)
    text = re.sub(r"^あいこ\s+(?=相手の)", "", text)

    # Strip trailing noise debris and sound effects
    text = re.sub(r"\s+[^\s]*[♪~].*$", "", text)
    text = re.sub(r"\s+[ぁ-んァ-ヶ一-龥a-zA-Z0-9]{1,2}(?:\s+[ぁ-んァ-ヶ一-龥a-zA-Z0-9]{1,2})*$", "", text)

    # Strip garbage single particles after particles (e.g. '〜は E バオッキー を' -> '〜は バオッキーを')
    text = re.sub(r"(?<=[はがの])\s+[a-zA-Z0-9ぁ-んァ-ヶ]\s+(?=[ァ-ヶ一-龥])", " ", text)
    text = re.sub(r"([ァ-ヶ一-龥]+)\s+([をがはとのに])\s+", r"\g<1>\g<2> ", text)

    # Word & Phrasing Normalizations (Official Pokemon Terms & General OCR Dictionaries)
    text = text.replace("下かった", "下がった")
    text = text.replace("勝つた", "勝った")
    text = text.replace("決まらなかつた", "決まらなかった")
    text = text.replace("つまく", "うまく")
    text = text.replace("ハツグノ", "バツグン")
    text = text.replace("ハツグン", "バツグン")
    text = text.replace("メカノノカ", "メガシンカ")
    text = text.replace("メガノノカ", "メガシンカ")
    text = text.replace("メカシンカ", "メガシンカ")
    text = text.replace("イリユ ノヨノ", "イリュージョン")
    text = text.replace("イリュ ノヨン", "イリュージョン")
    text = text.replace("ハオツキ", "バオッキー")
    text = text.replace("バオツキ", "バオッキー")
    text = text.replace("ソロア ク", "ゾロアーク")
    text = text.replace("ソロアーク", "ゾロアーク")
    text = text.replace("クチ トナイト", "クチートナイト")
    text = text.replace("メカクチ ト", "メガクチート")
    text = text.replace("メカクチート", "メガクチート")
    text = text.replace("メガクチ ト", "メガクチート")
    text = text.replace("選はれました", "選ばれました")

    # Grammar / Particle Corrections for Pokemon battle texts
    text = re.sub(r"攻撃[か|]\s*(下がった|上がった)", r"攻撃が \g<1>", text)
    text = re.sub(r"イリュージョン[か|]\s*解けた", "イリュージョンが 解けた", text)
    text = re.sub(r"降参[か|]\s*選ばれました", "降参が 選ばれました", text)
    text = re.sub(r"リング[か|]\s*反応した", "リングが 反応した", text)

    # Common Pokemon battle text end punctuation OCR corrections
    text = re.sub(r"ゆけ[つつっ][ノ川l!]+", "ゆけっ！", text)
    text = re.sub(r"(繰り出した|くりだした|勝った|かつた|負けた|反応した|メガシンカした|下がった|上がった|あたった|決まらなかった|たおれた|解けた|選ばれました|かわらわり|トリック)[ノ川l!]+", r"\g<1>！", text)
    text = re.sub(r"[ノ川]+$", "！", text)
    text = re.sub(r"([ァ-ヶー]{2,10})[ノ川]+(\s+|$)", r"\g<1>！\g<2>", text)

    # Clean popup texts (ability/item popups: strip internal spaces for all abilities/items)
    if side in ["player", "opponent"]:
        text = re.sub(r"\s+", "", text)

    # Clean double punctuation and extra spaces
    text = re.sub(r"！+", "！", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 2:
        return None

    return text


def extract_opponent_name(events: List[Dict[str, Any]]) -> str:
    """Infer opponent trainer name from all parsed battle events."""
    for ev in events:
        text = ev.get("text", "")
        if not text:
            continue

        patterns = [
            r"([^\s]{1,12})は\s+[^\s]{1,12}\s*を\s*(?:繰り出した|くりだした)",
            r"([^\s]{1,12})\s*との\s*勝負に\s*(?:勝った|かつた|負けた)",
            r"(?:相手の|あいての)?\s*(?:ポケモントレーナーの|トレーナーの)?\s*([^\s]{1,12})\s*(?:が|と)\s*(?:勝負|しょうぶ|をしかけて)",
            r"相手の\s*([^\s]{1,12})\s*が",
        ]

        for pat in patterns:
            match = re.search(pat, text)
            if match:
                candidate = match.group(1).strip()
                if candidate and candidate not in ["相手", "あいて", "自分", "じぶん", "ポケモン", "ゆけ", "もどれ", "ゆけっ"]:
                    sanitized = re.sub(r'[\\/:*?"<>|]', "", candidate)
                    if sanitized:
                        return sanitized

    return "opponent"


def extract_datetime_from_path(
    file_path: Union[str, Path], fallback_now: Optional[datetime] = None
) -> datetime:
    """Extract datetime from file path using filename patterns or OS metadata.

    Order of precedence:
    1. 6-component datetime patterns in filename (Android screen recordings, Switch, OBS, etc.)
    2. 3-component date patterns in filename (YYYY-MM-DD, YYYYMMDD)
    3. OS file metadata (earliest valid timestamp between mtime, ctime, birthtime)
    4. Fallback datetime (fallback_now or datetime.now())
    """
    path = Path(file_path)
    stem = path.stem

    # --- Step 1: Match 6-component datetime patterns (Year, Month, Day, Hour, Minute, Second) ---
    # 1a. Android & standard delimited formats (e.g., 'screen-20260831-222435-1788182376514', '20260831_222435')
    m = re.search(
        r"(?:^|[^\d])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[-_\sT]+([01]\d|2[0-3])([0-5]\d)([0-5]\d)(?:[^\d]|$)",
        stem,
    )
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
            )
        except ValueError:
            pass

    # 1b. Fully hyphenated/dotted/spaced datetime (e.g., 'Screenrecorder-2026-08-31-22-24-35', '2026-08-31 22:24:35', '2026-08-31_22-24-35')
    m = re.search(
        r"(?:^|[^\d])(20\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])[-_\sT]+([01]\d|2[0-3])[-_.:]([0-5]\d)[-_.:]([0-5]\d)(?:[^\d]|$)",
        stem,
    )
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
            )
        except ValueError:
            pass

    # 1c. Continuous 14-digit timestamp (e.g., Nintendo Switch '2026083122243500-...')
    m = re.search(
        r"(?:^|[^\d])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([01]\d|2[0-3])([0-5]\d)([0-5]\d)",
        stem,
    )
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
            )
        except ValueError:
            pass

    # --- Step 2: Match 3-component date patterns (Year, Month, Day) ---
    # 2a. Delimited date (e.g., '2026-08-31_battle', '2026.08.31', '2026_08_31')
    m = re.search(
        r"(?:^|[^\d])(20\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?:[^\d]|$)",
        stem,
    )
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 2b. Compact 8-digit date (e.g., '20260831_battle')
    m = re.search(
        r"(?:^|[^\d])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:[^\d]|$)",
        stem,
    )
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # --- Step 3: OS file metadata (stat) ---
    if path.exists() and path.is_file():
        try:
            stat = path.stat()
            timestamps = []
            if hasattr(stat, "st_mtime") and stat.st_mtime > 0:
                timestamps.append(stat.st_mtime)
            if hasattr(stat, "st_ctime") and stat.st_ctime > 0:
                timestamps.append(stat.st_ctime)
            if hasattr(stat, "st_birthtime") and stat.st_birthtime > 0:
                timestamps.append(stat.st_birthtime)

            if timestamps:
                earliest_ts = min(timestamps)
                dt = datetime.fromtimestamp(earliest_ts)
                if 2000 <= dt.year <= 2099:
                    return dt
        except Exception:
            pass

    # --- Step 4: Fallback ---
    return fallback_now if fallback_now is not None else datetime.now()


class BattleParser:
    """Parser that converts Pokemon battle videos/images into structured JSON events."""

    def __init__(
        self,
        ocr_processor: Optional[OCRProcessor] = None,
        roi_main: Tuple[float, float, float, float] = DEFAULT_ROI_MAIN,
        roi_popup_left: Tuple[float, float, float, float] = DEFAULT_ROI_POPUP_LEFT,
        roi_popup_right: Tuple[float, float, float, float] = DEFAULT_ROI_POPUP_RIGHT,
        roi_preview_center: Tuple[float, float, float, float] = DEFAULT_ROI_PREVIEW_CENTER,
        roi_preview_opponent: Tuple[float, float, float, float] = DEFAULT_ROI_PREVIEW_OPPONENT,
    ):
        self.ocr = ocr_processor or OCRProcessor()
        self.roi_main = roi_main
        self.roi_popup_left = roi_popup_left
        self.roi_popup_right = roi_popup_right
        self.roi_preview_center = roi_preview_center
        self.roi_preview_opponent = roi_preview_opponent

    def process_video(
        self,
        video_path: str,
        progress_callback: Optional[Callable[[float, Any], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
        sample_interval_sec: float = 0.8,
    ) -> Tuple[str, str, Dict[str, Any], Optional[np.ndarray]]:
        """Process a battle video file and extract text events into JSON."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(1, int(fps * sample_interval_sec))
        total_duration_sec = total_frames / fps if fps > 0 else 0.0

        events: List[Dict[str, Any]] = []
        last_states = {"main": "", "player": "", "opponent": ""}
        last_masks = {"main": None, "player": None, "opponent": None}
        last_ocr_results = {
            "main": {"text": "", "confidence": 0.0},
            "player": {"text": "", "confidence": 0.0},
            "opponent": {"text": "", "confidence": 0.0},
        }

        frame_count = 0
        start_real_time = time.time()
        total_paused_duration = 0.0
        best_preview_frame: Optional[np.ndarray] = None
        inferred_opponent_from_preview: str = ""
        battle_started: bool = False
        battle_ended: bool = False

        targets = [
            ("message", "field", self.roi_main, "main"),
            ("popup", "player", self.roi_popup_left, "player"),
            ("popup", "opponent", self.roi_popup_right, "opponent"),
        ]

        while cap.isOpened():
            # 1. Check for cancellation
            if cancel_event and cancel_event.is_set():
                break

            # 2. Check for pause
            if pause_event and not pause_event.is_set():
                pause_start = time.time()
                while not pause_event.is_set():
                    if cancel_event and cancel_event.is_set():
                        break
                    time.sleep(0.05)
                total_paused_duration += time.time() - pause_start
                if cancel_event and cancel_event.is_set():
                    break

            # Read only the target sample frame
            ret, frame = cap.read()
            if not ret:
                break

            time_sec = frame_count / fps
            timestamp_str = format_seconds(time_sec)

            # --- Detect 6on6 Team Preview Screen in first 35 seconds (checked only on full seconds) ---
            if time_sec <= 35.0 and best_preview_frame is None and (int(time_sec * 10) % 15 == 0):
                crop_center = crop_by_ratio(frame, self.roi_preview_center)
                mask_center = preprocess_and_remove_ruby(crop_center)
                if is_likely_text_mask(mask_center, min_char_count=3, min_pixels=250):
                    center_res = self.ocr.extract_text_from_mask(mask_center)
                    center_text = center_res.get("text", "")
                    if any(kw in center_text for kw in ["選出", "選んで", "3匹", "戦う", "ポケモン", "ランク"]):
                        best_preview_frame = frame.copy()
                        # Extract opponent trainer name from top-right badge
                        crop_opp = crop_by_ratio(frame, self.roi_preview_opponent)
                        opp_mask = preprocess_and_remove_ruby(crop_opp)
                        if is_likely_text_mask(opp_mask, min_char_count=1, min_pixels=60):
                            opp_res = self.ocr.extract_text_from_mask(opp_mask)
                            opp_text = opp_res.get("text", "").strip()
                            if opp_text and opp_text not in ["相手", "あいて", "つよさ", "表示"]:
                                sanitized = re.sub(r'[\\/:*?"<>|]', "", opp_text)
                                if sanitized:
                                    inferred_opponent_from_preview = sanitized

            for ev_type, side, roi, state_key in targets:
                # Check cancellation inside target loop
                if cancel_event and cancel_event.is_set():
                    break
                if pause_event and not pause_event.is_set():
                    pause_start = time.time()
                    while not pause_event.is_set():
                        if cancel_event and cancel_event.is_set():
                            break
                        time.sleep(0.05)
                    total_paused_duration += time.time() - pause_start
                    if cancel_event and cancel_event.is_set():
                        break

                crop = crop_by_ratio(frame, roi)
                mask = preprocess_and_remove_ruby(crop)
                min_p = 180 if state_key == "main" else 140

                # 1. Fast geometric check: skip immediately if it's just background light/noise
                if not is_likely_text_mask(mask, min_char_count=2, min_pixels=min_p):
                    res = {"text": "", "confidence": 0.0}
                    last_masks[state_key] = mask
                    last_ocr_results[state_key] = res
                else:
                    # 2. Image difference check against previous frame mask
                    prev_mask = last_masks[state_key]
                    pixel_count = cv2.countNonZero(mask)
                    if prev_mask is not None and prev_mask.shape == mask.shape:
                        diff = cv2.absdiff(mask, prev_mask)
                        diff_count = cv2.countNonZero(diff)
                        # Skip if difference is negligible (< 300px or < 12%)
                        if diff_count < 300 or (diff_count / max(pixel_count, 1) < 0.12):
                            res = last_ocr_results[state_key]
                        else:
                            res = self.ocr.extract_text_from_mask(mask)
                            last_masks[state_key] = mask
                            last_ocr_results[state_key] = res
                    else:
                        res = self.ocr.extract_text_from_mask(mask)
                        last_masks[state_key] = mask
                        last_ocr_results[state_key] = res

                raw_text = res["text"]
                clean_text = clean_battle_text(raw_text, res["confidence"], side)

                if clean_text and not battle_ended:
                    # Check for battle start
                    if not battle_started:
                        if any(kw in clean_text for kw in ["繰り出した", "くりだした", "勝負を", "しかけて", "ゆけっ", "現れた", "勝負に"]):
                            battle_started = True

                    # Only record events once battle has actively started (filters out team preview noise)
                    if battle_started:
                        if any(kw in clean_text for kw in ["勝負に 勝った", "勝負に 負けた", "勝負に勝った", "勝負に負けた", "対戦を 終了"]):
                            battle_ended = True

                        last_text = last_states[state_key]
                        sim = string_similarity(last_text, clean_text)

                        if events and events[-1]["side"] == side:
                            prev_ev = events[-1]
                            time_diff = round(time_sec, 2) - prev_ev.get("time_sec", 0.0)

                            # If same action/reaction message occurred within 2.5 seconds, update existing event instead of adding duplicate
                            if time_diff <= 2.5 and ("反応した！" in clean_text or "メガシンカ" in clean_text):
                                if len(clean_text) >= len(prev_ev["text"]):
                                    prev_ev["text"] = clean_text
                                    prev_ev["confidence"] = max(prev_ev["confidence"], res["confidence"])
                                last_states[state_key] = clean_text
                                continue

                        if sim < 0.75:
                            event_item = {
                                "timestamp": timestamp_str,
                                "time_sec": round(time_sec, 2),
                                "type": ev_type,
                                "side": side,
                                "text": clean_text,
                                "confidence": res["confidence"],
                            }
                            events.append(event_item)
                            last_states[state_key] = clean_text
                        elif len(clean_text) > len(last_text) and clean_text.startswith(last_text[: min(len(last_text), 4)]):
                            if events and events[-1]["side"] == side:
                                events[-1]["text"] = clean_text
                                events[-1]["confidence"] = max(events[-1]["confidence"], res["confidence"])
                                last_states[state_key] = clean_text

            if cancel_event and cancel_event.is_set():
                break

            frame_count += 1

            if progress_callback and total_frames > 0:
                prog = min(1.0, frame_count / total_frames)
                elapsed_sec = max(0.0, time.time() - start_real_time - total_paused_duration)
                if prog > 0.01:
                    eta_sec = (elapsed_sec / prog) * (1.0 - prog)
                else:
                    eta_sec = 0.0

                progress_info = {
                    "prog": prog,
                    "video_time_str": timestamp_str,
                    "video_duration_str": format_seconds(total_duration_sec),
                    "elapsed_str": format_seconds(elapsed_sec),
                    "eta_str": format_seconds(eta_sec) if prog > 0.01 else "--:--",
                    "events_count": len(events),
                    "has_preview": bool(best_preview_frame is not None),
                    "preview_frame": best_preview_frame if best_preview_frame is not None else None,
                }
                progress_callback(prog, progress_info)

            # Fast skip intervening frames without full decoding!
            frames_to_skip = frame_interval - 1
            for _ in range(frames_to_skip):
                if cancel_event and cancel_event.is_set():
                    break
                if not cap.grab():
                    break
                frame_count += 1

        cap.release()

        # Build metadata and final JSON
        opponent = extract_opponent_name(events)
        if opponent == "opponent" and inferred_opponent_from_preview:
            opponent = inferred_opponent_from_preview

        source_dt = extract_datetime_from_path(video_path)
        date_str = source_dt.strftime("%Y-%m-%d")
        default_filename = f"{date_str}_vs_{opponent}.json"

        battle_data: Dict[str, Any] = {
            "source": Path(video_path).name,
            "date": date_str,
            "recorded_at": source_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "opponent": opponent,
            "events_count": len(events),
            "events": events,
            "has_preview_image": bool(best_preview_frame is not None),
            "interrupted": bool(cancel_event and cancel_event.is_set()),
        }

        json_str = json.dumps(battle_data, ensure_ascii=False, indent=2)
        return json_str, default_filename, battle_data, best_preview_frame

    def process_images(
        self,
        image_paths: List[str],
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        pause_event: Optional[threading.Event] = None,
    ) -> Tuple[str, str, Dict[str, Any], Optional[np.ndarray]]:
        """Process a list of static screenshots in chronological order."""
        events: List[Dict[str, Any]] = []
        last_states = {"main": "", "player": "", "opponent": ""}
        best_preview_frame: Optional[np.ndarray] = None
        inferred_opponent_from_preview: str = ""
        total_images = len(image_paths)

        targets = [
            ("message", "field", self.roi_main, "main"),
            ("popup", "player", self.roi_popup_left, "player"),
            ("popup", "opponent", self.roi_popup_right, "opponent"),
        ]

        for idx, img_path in enumerate(image_paths):
            if cancel_event and cancel_event.is_set():
                break

            if pause_event and not pause_event.is_set():
                while not pause_event.is_set():
                    if cancel_event and cancel_event.is_set():
                        break
                    time.sleep(0.08)
                if cancel_event and cancel_event.is_set():
                    break

            frame = read_image_unicode(img_path)
            if frame is None:
                continue

            # Check if this static image is team preview screen
            if best_preview_frame is None:
                crop_center = crop_by_ratio(frame, self.roi_preview_center)
                mask_center = preprocess_and_remove_ruby(crop_center)
                if is_likely_text_mask(mask_center, min_char_count=3, min_pixels=250):
                    center_res = self.ocr.extract_text_from_mask(mask_center)
                    center_text = center_res.get("text", "")
                    if any(kw in center_text for kw in ["選出", "選んで", "3匹", "戦う", "ポケモン", "ランク"]):
                        best_preview_frame = frame.copy()
                        crop_opp = crop_by_ratio(frame, self.roi_preview_opponent)
                        opp_mask = preprocess_and_remove_ruby(crop_opp)
                        if is_likely_text_mask(opp_mask, min_char_count=1, min_pixels=60):
                            opp_res = self.ocr.extract_text_from_mask(opp_mask)
                            opp_text = opp_res.get("text", "").strip()
                            if opp_text and opp_text not in ["相手", "あいて", "つよさ", "表示"]:
                                sanitized = re.sub(r'[\\/:*?"<>|]', "", opp_text)
                                if sanitized:
                                    inferred_opponent_from_preview = sanitized

            timestamp_str = f"img_{idx + 1:03d}"

            for ev_type, side, roi, state_key in targets:
                crop = crop_by_ratio(frame, roi)
                mask = preprocess_and_remove_ruby(crop)
                min_p = 180 if state_key == "main" else 140

                if not is_likely_text_mask(mask, min_char_count=2, min_pixels=min_p):
                    text = ""
                    res = {"text": "", "confidence": 0.0}
                else:
                    res = self.ocr.extract_text_from_mask(mask)
                    raw_text = res["text"]
                    text = clean_battle_text(raw_text, res["confidence"], side) or ""

                if text:
                    last_text = last_states[state_key]
                    sim = string_similarity(last_text, text)
                    if sim < 0.75:
                        events.append(
                            {
                                "timestamp": timestamp_str,
                                "file_name": Path(img_path).name,
                                "type": ev_type,
                                "side": side,
                                "text": text,
                                "confidence": res["confidence"],
                            }
                        )
                        last_states[state_key] = text

            if progress_callback and total_images > 0:
                prog = (idx + 1) / total_images
                progress_callback(prog, f"画像処理中... ({idx + 1}/{total_images})")

        opponent = extract_opponent_name(events)
        if opponent == "opponent" and inferred_opponent_from_preview:
            opponent = inferred_opponent_from_preview

        first_img = image_paths[0] if image_paths else ""
        source_dt = extract_datetime_from_path(first_img) if first_img else datetime.now()
        date_str = source_dt.strftime("%Y-%m-%d")
        default_filename = f"{date_str}_vs_{opponent}.json"

        battle_data: Dict[str, Any] = {
            "source": f"images_batch_{len(image_paths)}",
            "date": date_str,
            "recorded_at": source_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "opponent": opponent,
            "events_count": len(events),
            "events": events,
            "has_preview_image": bool(best_preview_frame is not None),
            "interrupted": bool(cancel_event and cancel_event.is_set()),
        }

        json_str = json.dumps(battle_data, ensure_ascii=False, indent=2)
        return json_str, default_filename, battle_data, best_preview_frame
