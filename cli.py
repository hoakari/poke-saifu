"""Command Line Interface for Poke-Saifu.

Enables batch and headless execution to convert battle videos or screenshot folders to JSON.
"""

import argparse
import glob
import os
from pathlib import Path
import sys
from typing import Any
from poke_saifu.parser import BattleParser


def main():
    parser = argparse.ArgumentParser(
        description="Poke-Saifu: ポケモン対戦動画/画像からイベントログを抽出してJSON化するCLIツール"
    )
    parser.add_argument(
        "input_path",
        help="解析対象の動画ファイルパス (.mp4, .mov等) または画像群のディレクトリ/ワイルドカード",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="出力先JSONファイルパス (省略時は input と同じ場所にデフォルト命名で保存)",
        default=None,
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="GPUを使わずに強制的にCPUでOCRを実行",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="選出見せ合い画像の自動出力を無効化（JSONのみ出力）",
    )
    parser.add_argument(
        "--preview-dir",
        help="選出見せ合い画像の保存先ディレクトリ（省略時はJSONと同じ場所）",
        default=None,
    )

    args = parser.parse_args()

    input_path = args.input_path
    battle_parser = BattleParser()
    if args.cpu:
        battle_parser.ocr.gpu = False

    def progress_callback(prog: float, info: Any):
        bar_len = 25
        filled = int(bar_len * prog)
        bar = "=" * filled + "-" * (bar_len - filled)
        if isinstance(info, dict):
            video_time = info.get("video_time_str", "00:00")
            video_dur = info.get("video_duration_str", "00:00")
            elapsed = info.get("elapsed_str", "00:00")
            eta = info.get("eta_str", "--:--")
            events_cnt = info.get("events_count", 0)
            msg = f"動画 {video_time}/{video_dur} | 経過 {elapsed} (残り約 {eta}) | 検出 {events_cnt}件"
        else:
            msg = str(info)
        sys.stdout.write(f"\r[{bar}] {int(prog * 100):3d}% | {msg}")
        sys.stdout.flush()

    print(f"[*] Poke-Saifu 開始: {input_path}")

    # Check if input is a directory or glob pattern for images
    if os.path.isdir(input_path):
        exts = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"]
        images = []
        for ext in exts:
            images.extend(sorted(glob.glob(os.path.join(input_path, ext))))
        if not images:
            print(f"[!] エラー: ディレクトリ内に画像が見つかりませんでした: {input_path}")
            sys.exit(1)
        print(f"[*] 対象画像数: {len(images)} 枚")
        json_str, default_name, _, preview_frame = battle_parser.process_images(
            images, progress_callback=progress_callback
        )
    elif any(char in input_path for char in ["*", "?", "["]):
        images = sorted(glob.glob(input_path))
        if not images:
            print(f"[!] エラー: パターンに一致するファイルがありません: {input_path}")
            sys.exit(1)
        json_str, default_name, _, preview_frame = battle_parser.process_images(
            images, progress_callback=progress_callback
        )
    elif os.path.isfile(input_path):
        ext = Path(input_path).suffix.lower()
        if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
            json_str, default_name, _, preview_frame = battle_parser.process_video(
                input_path, progress_callback=progress_callback
            )
        else:
            json_str, default_name, _, preview_frame = battle_parser.process_images(
                [input_path], progress_callback=progress_callback
            )
    else:
        print(f"[!] エラー: 対象ファイルまたはディレクトリが存在しません: {input_path}")
        sys.exit(1)

    print("\n[*] 解析完了！")

    out_path = args.output
    if not out_path:
        out_dir = Path(input_path).parent if os.path.isfile(input_path) else Path(input_path)
        out_path = str(out_dir / default_name)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    print(f"[*] JSONを出力しました: {out_path}")

    # Auto-save 6on6 team preview screenshot
    if preview_frame is not None and not args.no_preview:
        from poke_saifu.core import save_image_unicode

        if args.preview_dir:
            p_dir = Path(args.preview_dir)
            p_dir.mkdir(parents=True, exist_ok=True)
            img_out_path = p_dir / f"{Path(out_path).stem}_preview.png"
        else:
            img_out_path = Path(out_path).with_name(f"{Path(out_path).stem}_preview.png")

        save_image_unicode(img_out_path, preview_frame)
        print(f"[*] 見せ合い画像を保存しました: {img_out_path}")


if __name__ == "__main__":
    main()
