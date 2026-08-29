# Poke-Saifu (ポケモン採譜) 🎴

> **ポケモン対戦動画・スクショからテキストログを抽出し、時系列JSONへ変換する軽量GUIデスクトップツール**

---

## 概要

Claudeや各種LLMに対戦スクショを大量に読み込ませると莫大な画像トークン（1戦あたり5万〜8万トークン）を消費します。  
**Poke-Saifu** は、ローカル環境で動画・画像から「メインメッセージ領域」および「左右の特性・持ち物ポップアップ」を高精度に抽出し、テキストJSON（約1,000〜3,000トークン）に変換します。

### 特徴
- 🎯 **ノーメンテナンス設計**: ポケモン名や技名の静的辞書・レギュレーションを持たず、純粋な画像処理（白・黄色のHSVカラーマスク＋幾何学的ルビ除去）とOCRのみで動作。新作やDLCが出てもコード修正不要。
- 🖼️ **6on6選出見せ合い画面の自動キャプチャ**: 試合序盤の選出画面（相手パーティ6体＋自分の持ち物）を自動検出し、GUI上にサムネイル表示。JSON保存時にペア画像（`_preview.png`）として自動保存。
- ⚡ **超高速フレームスキップ**: `cap.grab()` による不要フレームのデコードスキップ＆幾何学的文字判定で、実時間の数倍速で高速処理。
- ⏸️ **中断・再開・クリア機能**: 解析途中の一時停止、続きからの再開、動画選択前状態への完全リセットに対応。
- 🖱️ **直感的なGUI**: 動画やスクショ画像をドラッグ＆ドロップするだけで自動解析。
- 📋 **チェックボックス保存・コピー**: 見せ合い画像とJSONの保存をチェックボックスで柔軟に選択可能。
- 📦 **Windows単体exe対応**: PyInstallerによるビルドスクリプト同梱。

---

## ⚠️ 動作環境と認識精度について (Current Status)

- **動作確認プラットフォーム**:
  - 現在のバージョンは主に **Android版『Pokémon Champions』**（16:9 画面録画・スクリーンショット）を前提に座標領域（ROI）および文字認識の調整・動作確認を行っています。
  - 16:9以外のアスペクト比や別プラットフォームの映像では、認識領域にズレが生じる場合があります。
- **現在の認識精度（Beta版）**:
  - 本ツールは開発途上であり、激しい技演出や背景の光エフェクト、フォントのレンダリング状況によってOCRの誤読（軽微な文字揺らぎ）や未検出が発生する場合があります。
  - **LLM連携時のTips**: 抽出したJSONをClaudeやChatGPT等に渡す際、プロンプトに **「※OCRログのため軽微な文字揺らぎ（クチ トナイト→クチートナイト等）を文脈から補正して解釈してください」** と一言添えることで、LLM側の文脈補正により極めて安定した戦術分析や採譜が可能です。
  - 誤読パターンや改善のご要望・フィードバック（Issues）を歓迎しています。

---

## ディレクトリ構成

```plaintext
poke-saifu/
├── assets/                  # アプリアイコン (icon.ico, icon.png)
├── poke_saifu/
│   ├── assets/              # パッケージ同梱用アイコン
│   ├── core.py              # カラーマスク、ルビ除去、ROIクロップ、OCR処理
│   ├── parser.py            # 動画/画像解析、選出画面検知、重複排除、JSON生成
│   └── gui.py               # TkinterDnD2ベースのGUIコンポーネント・アプリ本体
├── tests/                   # 単体テストスクリプト
├── app.py                   # GUI起動エントリーポイント
├── cli.py                   # CLI実行用エントリーポイント（自動化・バッチ用）
├── Poke-Saifu.spec          # PyInstaller spec設定ファイル
├── build_exe.bat            # PyInstaller exe化ビルドスクリプト
├── requirements.txt         # 依存パッケージ一覧
└── README.md                # 使い方ガイド
```

## インストール & 実行方法

### 1. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 2. GUIアプリの起動
```bash
python app.py
```

### 3. CLI（コマンドライン）での実行
バッチ処理や自動化に便利です（選出見せ合い画像も自動でペア保存されます）。

```bash
# 動画を解析してJSON＋見せ合い画像（_preview.png）をペア出力
python cli.py "path/to/battle_video.mp4"

# 出力ファイル名を指定する場合
python cli.py "path/to/battle_video.mp4" -o "custom_output.json"

# 画像の自動保存を無効化し、JSONのみ出力する場合
python cli.py "path/to/battle_video.mp4" --no-preview

# スクショ画像フォルダを一括処理
python cli.py "path/to/screenshots_folder"
```

---

## Windows EXE化の手順

同梱の `build_exe.bat` をダブルクリックして実行するか、以下のコマンドを実行してください。

```bash
pyinstaller --noconfirm Poke-Saifu.spec
```

ビルド完了後、`dist/Poke-Saifu/Poke-Saifu.exe` が生成されます。

---

## 出力されるJSONフォーマット例

```json
{
  "source": "2026-08-29_battle.mp4",
  "date": "2026-08-29",
  "opponent": "シゲル",
  "events_count": 4,
  "events": [
    {
      "timestamp": "00:12",
      "time_sec": 12.0,
      "type": "popup",
      "side": "opponent",
      "text": "すりぬけ",
      "confidence": 0.95
    },
    {
      "timestamp": "00:14",
      "time_sec": 14.5,
      "type": "message",
      "side": "field",
      "text": "相手の シャンデラの 特攻が がくっと下がった！",
      "confidence": 0.92
    },
    {
      "timestamp": "00:18",
      "time_sec": 18.0,
      "type": "message",
      "side": "field",
      "text": "急所に あたった！",
      "confidence": 0.94
    },
    {
      "timestamp": "00:22",
      "time_sec": 22.5,
      "type": "popup",
      "side": "player",
      "text": "きあいのタスキ",
      "confidence": 0.88
    }
  ]
}
```

---

## 免責事項 (Disclaimer)

- 本ツールは個人が開発した非公式のファンメイドツールであり、任天堂株式会社、株式会社ポケモン、株式会社ゲームフリーク、株式会社クリーチャーズとは一切関係ありません。
- 「ポケットモンスター」「ポケモン」「Pokémon」は、任天堂・クリーチャーズ・ゲームフリークの登録商標です。
- 本リポジトリにはゲームのROM、公式画像、音声等の著作物アセットは一切含まれておらず、ユーザーがローカルで用意した動画・画像の解析のみを行います。

---

## ライセンス (License)

[MIT License](LICENSE) © 2026 hoakari
