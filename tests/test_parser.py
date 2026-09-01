"""Unit tests for Poke-Saifu core and parser modules."""

import numpy as np
import pytest

from poke_saifu.core import (
    DEFAULT_ROI_MAIN,
    crop_by_ratio,
    preprocess_and_remove_ruby,
)
from poke_saifu.parser import extract_opponent_name, string_similarity


def test_string_similarity():
    assert string_similarity("シャンデラ", "シャンデラ") == 1.0
    assert string_similarity("シャンデラ", "シャンデラの") > 0.8
    assert string_similarity("ピカチュウ", "カイリュー") < 0.5
    assert string_similarity("", "") == 1.0
    assert string_similarity("abc", "") == 0.0


def test_extract_opponent_name():
    events_1 = [
        {"text": "ポケモントレーナーの サトシが 勝負を しかけてきた！"},
        {"text": "サトシは ピカチュウを くりだした！"},
    ]
    assert extract_opponent_name(events_1) == "サトシ"

    events_2 = [
        {"text": "相手の シゲルが 勝負を くりだした！"},
    ]
    assert extract_opponent_name(events_2) == "シゲル"

    events_3 = [
        {"text": "急所に あたった！"},
        {"text": "こうかは ばつぐんだ！"},
    ]
    assert extract_opponent_name(events_3) == "opponent"


def test_crop_by_ratio():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = crop_by_ratio(frame, DEFAULT_ROI_MAIN)
    # ymin: 0.68*1080=734.4 -> 734, ymax: 0.88*1080=950.4 -> 950
    # xmin: 0.18*1920=345.6 -> 345, xmax: 0.58*1920=1113.6 -> 1113
    assert crop.shape[0] > 0
    assert crop.shape[1] > 0
    assert crop.shape[2] == 3


def test_preprocess_and_remove_ruby():
    # Create test image with dummy white and yellow areas
    img = np.zeros((100, 300, 3), dtype=np.uint8)

    # Add white text block (large height, should be retained)
    img[40:80, 50:200] = [255, 255, 255]

    # Add ruby tiny block (small height < 15px at 2x scale, should be removed)
    img[10:14, 60:120] = [255, 255, 255]

    mask = preprocess_and_remove_ruby(img, scale_factor=2.0, ruby_height_threshold=15)
    assert mask.shape == (200, 600)
    # The main block should produce non-zero pixels
    assert np.count_nonzero(mask) > 0


class MockOCRProcessor:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    def extract_text(self, crop_bgr):
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
            self.call_count += 1
            return res
        return {"text": "", "confidence": 0.0}

    def extract_text_from_mask(self, binary_mask):
        return self.extract_text(binary_mask)


def test_battle_parser_flow(tmp_path):
    import json
    import cv2
    from poke_saifu.parser import BattleParser

    # Create 2 dummy images with white text-like blocks
    img1_path = str(tmp_path / "frame1.png")
    img2_path = str(tmp_path / "frame2.png")
    dummy_frame1 = np.zeros((720, 1280, 3), dtype=np.uint8)
    dummy_frame2 = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Draw white text blocks in main message ROI (ymin: 0.68*720=490, xmin: 0.18*1280=230)
    for offset in [0, 40, 80, 120]:
        dummy_frame1[520:560, 250 + offset : 275 + offset] = [255, 255, 255]

    for offset in [0, 50, 100, 150, 200]:
        dummy_frame2[500:540, 240 + offset : 265 + offset] = [255, 255, 255]

    # Draw left popup (ymin: 0.33*720=238, xmin: 0.01*1280=13)
    for offset in [0, 30, 60]:
        dummy_frame2[260:290, 30 + offset : 50 + offset] = [255, 255, 255]

    cv2.imwrite(img1_path, dummy_frame1)
    cv2.imwrite(img2_path, dummy_frame2)

    # Mock responses for actual text-containing targets:
    # 1. Frame 1 main -> "ポケモントレーナーの シゲルが 勝負を しかけてきた！"
    # 2. Frame 2 main -> "急所に あたった！"
    # 3. Frame 2 player -> "きあいのタスキ"
    mock_ocr = MockOCRProcessor([
        {"text": "ポケモントレーナーの シゲルが 勝負を しかけてきた！", "confidence": 0.95},
        {"text": "急所に あたった！", "confidence": 0.92},
        {"text": "きあいのタスキ", "confidence": 0.88},
    ])

    parser = BattleParser(ocr_processor=mock_ocr)
    json_str, default_filename, data, preview_frame = parser.process_images([img1_path, img2_path])

    assert data["opponent"] == "シゲル"
    assert "vs_シゲル.json" in default_filename
    assert data["events_count"] == 3
    assert len(data["events"]) == 3
    assert data["events"][0]["text"] == "ポケモントレーナーの シゲルが 勝負を しかけてきた！"
    assert data["events"][0]["type"] == "message"
    assert data["events"][1]["text"] == "急所に あたった！"
    assert data["events"][2]["text"] == "きあいのタスキ"
    assert data["events"][2]["type"] == "popup"
    assert data["events"][2]["side"] == "player"

    # Verify valid JSON
    parsed = json.loads(json_str)
    assert parsed["opponent"] == "シゲル"


def test_asset_paths():
    from poke_saifu.gui import get_asset_path
    ico = get_asset_path("icon.ico")
    png = get_asset_path("icon.png")
    assert ico.exists()
    assert png.exists()


def test_cancel_event(tmp_path):
    import threading
    import cv2
    from poke_saifu.parser import BattleParser

    img_paths = []
    for i in range(5):
        p = str(tmp_path / f"frame_{i}.png")
        cv2.imwrite(p, np.zeros((100, 100, 3), dtype=np.uint8))
        img_paths.append(p)

    cancel_ev = threading.Event()
    cancel_ev.set()  # Cancel immediately

    parser = BattleParser(ocr_processor=MockOCRProcessor([]))
    json_str, _, data, _ = parser.process_images(img_paths, cancel_event=cancel_ev)

    assert data["interrupted"] is True
    assert data["events_count"] == 0


def test_team_preview_detection(tmp_path):
    import cv2
    from poke_saifu.parser import BattleParser

    img_path = str(tmp_path / "preview.png")
    # Create a 16:9 dummy image with white text blocks in center and top-right
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    # Center ROI: ymin: 0.16*720=115, xmin: 0.35*1280=448
    for offset in [0, 30, 60, 90]:
        img[140:180, 480 + offset : 500 + offset] = [255, 255, 255]
    # Opponent ROI: ymin: 0.07*720=50, xmin: 0.72*1280=921
    for offset in [0, 25, 50]:
        img[60:90, 940 + offset : 960 + offset] = [255, 255, 255]

    cv2.imwrite(img_path, img)

    # Mock OCR returning team preview keyword for center ROI
    mock_ocr = MockOCRProcessor([
        {"text": "戦うポケモンを 3匹 選出してください", "confidence": 0.99},
        {"text": "ワタル", "confidence": 0.95},
    ])

    parser = BattleParser(ocr_processor=mock_ocr)
    json_str, filename, data, preview_frame = parser.process_images([img_path])

    assert data["has_preview_image"] is True
    assert preview_frame is not None
    assert data["opponent"] == "ワタル"
    assert "vs_ワタル.json" in filename


def test_clean_battle_text():
    from poke_saifu.parser import clean_battle_text

    # Valid message cleaning for generic official Pokemon battle texts
    assert clean_battle_text("相手は E ハオツキ を 繰り出した！", 0.67, "field") == "相手は バオッキーを 繰り出した！"
    assert clean_battle_text("ゆけつノ ピカチュウ！", 0.50, "field") == "ゆけっ！ ピカチュウ！"
    assert clean_battle_text("いかく 瀬", 0.67, "player") == "いかく"
    assert clean_battle_text("い 相手の バオツキ の さ 攻撃か 下がった！", 0.61, "field") == "相手の バオッキーの 攻撃が 下がった！"
    assert clean_battle_text("クチ トナイトと リングか 反応した！ トニーューー♪", 0.73, "field") == "クチートナイトと リングが 反応した！"
    assert clean_battle_text("メカクチ トに メカノノカした！", 0.76, "field") == "メガクチートに メガシンカした！"
    assert clean_battle_text("r 相手の ハオツキ の トリック！", 0.81, "field") == "相手の バオッキーの トリック！"
    assert clean_battle_text("しかし つまく 決まらなかった！", 0.79, "field") == "しかし うまく 決まらなかった！"
    assert clean_battle_text("い 相手の ソロア クの こ イリュージョンか 解けた！", 0.69, "field") == "相手の ゾロアークの イリュージョンが 解けた！"
    assert clean_battle_text("あいこ 相手の ソロア クは たおれた！", 0.97, "field") == "相手の ゾロアークは たおれた！"
    assert clean_battle_text("降参か 選はれました", 0.83, "field") == "降参が 選ばれました"
    assert clean_battle_text("相手との 勝負に 勝つたノ", 0.79, "field") == "相手との 勝負に 勝った！"
    assert clean_battle_text("効果は ハツグノだノ", 0.86, "field") == "効果は バツグンだ！"

    # Noise discarding
    assert clean_battle_text("口", 0.33, "player") is None
    assert clean_battle_text("び ル' o @", 0.37, "field") is None
    assert clean_battle_text("※はるreacheda14 Friend Streakv ロn Cnnnratlllatetheml day", 0.48, "field") is None
    assert clean_battle_text("拝子を比る", 0.04, "opponent") is None
    assert clean_battle_text("1 07 oo", 0.43, "field") is None
    assert clean_battle_text("心 ・", 0.11, "opponent") is None


def test_unicode_image_io(tmp_path):
    from poke_saifu.core import read_image_unicode, save_image_unicode

    # Japanese Unicode path test
    jp_path = tmp_path / "2026-08-29_vs_ワタル_preview.png"
    dummy = np.zeros((100, 100, 3), dtype=np.uint8)
    dummy[20:80, 20:80] = [0, 255, 0]

    assert save_image_unicode(jp_path, dummy) is True
    assert jp_path.exists()
    assert "ワタル" in jp_path.name

    loaded = read_image_unicode(jp_path)
    assert loaded is not None
    assert loaded.shape == (100, 100, 3)


def test_extract_datetime_from_path_patterns():
    from datetime import datetime
    from poke_saifu.parser import extract_datetime_from_path

    # Android screen recording formats
    dt1 = extract_datetime_from_path("screen-20260831-222435-1788182376514.mp4")
    assert dt1 == datetime(2026, 8, 31, 22, 24, 35)

    dt2 = extract_datetime_from_path("Screenrecorder-2026-08-31-22-24-35.mp4")
    assert dt2 == datetime(2026, 8, 31, 22, 24, 35)

    dt3 = extract_datetime_from_path("Screen_Recording_20260831_222435.mp4")
    assert dt3 == datetime(2026, 8, 31, 22, 24, 35)

    dt4 = extract_datetime_from_path("Screenshot_20260831-222435.png")
    assert dt4 == datetime(2026, 8, 31, 22, 24, 35)

    # Nintendo Switch capture format (14-digit timestamp + sequence/hash)
    dt5 = extract_datetime_from_path("2026083122243500-ABCDEF123456.mp4")
    assert dt5 == datetime(2026, 8, 31, 22, 24, 35)

    # General delimited formats
    dt6 = extract_datetime_from_path("2026-08-31 22.24.35.mp4")
    assert dt6 == datetime(2026, 8, 31, 22, 24, 35)

    dt7 = extract_datetime_from_path("battle_2026-08-31_22-24-35.mov")
    assert dt7 == datetime(2026, 8, 31, 22, 24, 35)

    # Date-only formats
    dt8 = extract_datetime_from_path("2026-08-31_battle.mp4")
    assert dt8 == datetime(2026, 8, 31, 0, 0, 0)

    dt9 = extract_datetime_from_path("20260831_battle.mp4")
    assert dt9 == datetime(2026, 8, 31, 0, 0, 0)


def test_extract_datetime_from_path_os_stat_and_fallback(tmp_path):
    from datetime import datetime
    from poke_saifu.parser import extract_datetime_from_path

    # Fallback when file doesn't exist and filename has no date
    fallback_dt = datetime(2025, 1, 1, 12, 0, 0)
    dt_fallback = extract_datetime_from_path("undated_video.mp4", fallback_now=fallback_dt)
    assert dt_fallback == fallback_dt

    # When real file exists without date in name, should use stat metadata
    test_file = tmp_path / "custom_recording.mp4"
    test_file.write_text("dummy video content")
    dt_stat = extract_datetime_from_path(test_file)
    assert dt_stat.year >= 2020


def test_battle_parser_uses_source_datetime(tmp_path):
    import cv2
    from poke_saifu.parser import BattleParser

    img_path = str(tmp_path / "screen-20260831-222435-1788182376514.png")
    cv2.imwrite(img_path, np.zeros((720, 1280, 3), dtype=np.uint8))

    parser = BattleParser(ocr_processor=MockOCRProcessor([]))
    json_str, default_filename, data, _ = parser.process_images([img_path])

    assert data["date"] == "2026-08-31"
    assert data["recorded_at"] == "2026-08-31 22:24:35"
    assert default_filename.startswith("2026-08-31_vs_")


def test_team_preview_retry_loop(tmp_path):
    """Test that team preview is retrieved during the retry phase if missed in initial pass, without modifying JSON events."""
    import cv2
    from poke_saifu.parser import BattleParser

    video_path = str(tmp_path / "battle_retry_test.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 10.0
    out = cv2.VideoWriter(video_path, fourcc, fps, (1280, 720))

    # Frame 0 to 4 (0.0s - 0.4s): Blank
    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for _ in range(5):
        out.write(blank_frame)

    # Frame 5 (0.5s): Team Preview screen
    preview_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for offset in [0, 30, 60, 90]:
        preview_frame[140:180, 480 + offset : 500 + offset] = [255, 255, 255]
    for offset in [0, 25, 50]:
        preview_frame[60:90, 940 + offset : 960 + offset] = [255, 255, 255]
    out.write(preview_frame)

    # Frame 6 to 9 (0.6s - 0.9s): Blank
    for _ in range(4):
        out.write(blank_frame)

    # Frame 10 to 19 (1.0s - 1.9s): Battle start message
    battle_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for offset in [0, 40, 80, 120]:
        battle_frame[520:560, 250 + offset : 275 + offset] = [255, 255, 255]
    for _ in range(10):
        out.write(battle_frame)

    out.release()

    # In initial pass with sample_interval_sec=1.0:
    # Samples at 0.0s (Frame 0: Blank) and 1.0s (Frame 10: Battle start)
    # The preview screen at Frame 5 (0.5s) is missed during initial pass!
    # Retry loop should scan from 0.0s to 1.0s (first event time) and successfully detect it.

    class DynamicMockOCR(MockOCRProcessor):
        def __init__(self):
            super().__init__([])

        def extract_text_from_mask(self, binary_mask: np.ndarray):
            # If mask is in preview center ROI (288, 640)
            if binary_mask.shape[1] <= 640:
                return {"text": "戦うポケモンを 3匹 選出してください", "confidence": 0.98}
            # If mask is in main message ROI (288, 1024)
            return {"text": "ポケモントレーナーの シゲルが 勝負を しかけてきた！", "confidence": 0.95}

    parser = BattleParser(ocr_processor=DynamicMockOCR())
    json_str, filename, data, found_preview = parser.process_video(
        video_path, sample_interval_sec=1.0
    )

    # Verify preview frame was successfully acquired via retry loop
    assert found_preview is not None
    assert data["has_preview_image"] is True
    # Verify JSON events were NOT polluted or modified by the retry loop
    assert data["events_count"] == 1
    assert len(data["events"]) == 1
    assert data["events"][0]["text"] == "ポケモントレーナーの シゲルが 勝負を しかけてきた！"
    assert data["events"][0]["time_sec"] == 1.0


def test_team_preview_retry_not_found(tmp_path):
    """Test that if team preview is never found, parser finishes gracefully after 3 retry attempts."""
    import cv2
    from poke_saifu.parser import BattleParser

    video_path = str(tmp_path / "battle_no_preview.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 10.0
    out = cv2.VideoWriter(video_path, fourcc, fps, (1280, 720))

    # All frames are blank or simple messages
    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for _ in range(15):
        out.write(blank_frame)
    out.release()

    parser = BattleParser(ocr_processor=MockOCRProcessor([]))
    json_str, filename, data, found_preview = parser.process_video(video_path, sample_interval_sec=0.5)

    assert found_preview is None
    assert data["has_preview_image"] is False
    assert data["events_count"] == 0


def test_team_preview_retry_with_no_events(tmp_path):
    """Test retry search when there are no battle events detected."""
    import cv2
    from poke_saifu.parser import BattleParser

    video_path = str(tmp_path / "preview_only.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = 10.0
    out = cv2.VideoWriter(video_path, fourcc, fps, (1280, 720))

    # Frame 0 to 2: Blank
    blank_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for _ in range(3):
        out.write(blank_frame)

    # Frame 3: Preview screen
    preview_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for offset in [0, 30, 60, 90]:
        preview_frame[140:180, 480 + offset : 500 + offset] = [255, 255, 255]
    out.write(preview_frame)

    # Frame 4 to 10: Blank
    for _ in range(7):
        out.write(blank_frame)
    out.release()

    class PreviewOnlyMockOCR(MockOCRProcessor):
        def __init__(self):
            super().__init__([])

        def extract_text_from_mask(self, binary_mask: np.ndarray):
            if binary_mask.shape[1] <= 640:
                return {"text": "戦うポケモンを 3匹 選出してください", "confidence": 0.98}
            return {"text": "", "confidence": 0.0}

    parser = BattleParser(ocr_processor=PreviewOnlyMockOCR())
    json_str, filename, data, found_preview = parser.process_video(video_path, sample_interval_sec=1.0)

    assert found_preview is not None
    assert data["has_preview_image"] is True
    assert data["events_count"] == 0






