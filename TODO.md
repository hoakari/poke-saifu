# Poke-Saifu 開発ロードマップ & 課題管理 (Issues)

Poke-Saifu の不具合修正・精度改善および機能拡張タスク一覧です。  
詳細な議論、再現ログ、進捗追跡はすべて [GitHub Issues](https://github.com/hoakari/poke-saifu/issues) にて一元管理しています。

---

## 🐛 既知の不具合・精度改善 (Bug & Accuracy)

| Issue | タイトル | ラベル | 優先度 |
| :--- | :--- | :--- | :--- |
| [#1](https://github.com/hoakari/poke-saifu/issues/1) | [OCR/Bug] 技選択画面や固定UI要素（「用語の説明 閉じろ」「バルデアチヤノピオ」等）が誤読ノイズとして記録される | `bug` `ocr` `accuracy` | 高 |
| [#2](https://github.com/hoakari/poke-saifu/issues/2) | [OCR/Bug] confidence 0.28前後の特定不能な極低信頼度ノイズ行が混入する | `bug` `ocr` | 高 |
| [#3](https://github.com/hoakari/poke-saifu/issues/3) | [Logic/Bug] 同一メッセージが連続して2〜3回記録される準重複事象（重複排除のすり抜け） | `bug` `accuracy` | 高 |
| [#4](https://github.com/hoakari/poke-saifu/issues/4) | [Logic/Bug] 両陣営が短時間でメガシンカした際、確定メッセージ（「メガ○○にメガシンカした！」）が欠落・混線する | `bug` `accuracy` | 高 |
| [#5](https://github.com/hoakari/poke-saifu/issues/5) | [Logic/Bug] 多段技KO時等にイベント順序が前後逆転することがある（「たおれた」が先に来る等） | `bug` `accuracy` | 中 |
| [#6](https://github.com/hoakari/poke-saifu/issues/6) | [Logic/Bug] タイムアウト決着時に終了メッセージ（「〜との勝負に勝った」）が欠落することがある | `bug` `accuracy` | 中 |
| [#7](https://github.com/hoakari/poke-saifu/issues/7) | [OCR/Enhancement] 同一動画内でポケモン種族名の誤読パターンが崩れる問題への辞書ファジーマッチング補正 | `enhancement` `ocr` `accuracy` | 中 |
| [#8](https://github.com/hoakari/poke-saifu/issues/8) | [OCR/Discussion] ハングル（韓国語）等の非日本語トレーナー名のOCR崩壊および多言語対応方針 | `ocr` `question` | 要検討 |

---

## 🚀 新機能・機能拡張 (Features & CI/CD)

| Issue | タイトル | ラベル |
| :--- | :--- | :--- |
| [#9](https://github.com/hoakari/poke-saifu/issues/9) | [Feature] 選出見せ合い画面（6on6）のOCR解析およびJSON構造化出力 | `feature` `ocr` |
| [#12](https://github.com/hoakari/poke-saifu/issues/12) | [CI/CD] GitHub Actions による Windows 用 exe の自動ビルド＆Releases 配布 | `feature` |
| [#13](https://github.com/hoakari/poke-saifu/issues/13) | [Feature] GUIアプリ内での最新バージョン確認＆アップデート通知 | `feature` `ui` |

---

## 📅 完了済みタスク (Done)

- [x] **複数動画のキュー登録・連続自動解析＆完了通知機能 ([#10](https://github.com/hoakari/poke-saifu/issues/10))**
  - 複数動画の一括ドラッグ＆ドロップおよびファイル選択ダイアログからのキュー追加
  - 右側スライド「📋 処理キュー」パネル（進捗表示、ドラッグ並び替え、個別削除、クリア）
  - 1戦終了ごとの自動連続バッチ解析
  - 解析完了時の通知音（SE）、Windowsトースト通知（対戦相手・イベント数表示）、タスクバー点滅通知
- [x] **解析完了時の指定フォルダへの自動保存＆フォルダオープン ([#11](https://github.com/hoakari/poke-saifu/issues/11))**
  - 解析完了時のJSON・選出見せ合い画像（`_preview.png`）の自動保存（保存先フォルダ指定・設定記憶対応）
  - 「📁 保存フォルダを開く」ボタンによる出力先フォルダの即時表示
- [x] **入力ファイル（Android画面録画・Switch等）の日時自動抽出＆スマートファイル命名 ([#14](https://github.com/hoakari/poke-saifu/issues/14))**
  - Android録画形式（`screen-YYYYMMDD-HHMMSS-*.mp4` 等）やSwitch録画ファイル名からの日時自動パース
  - OSメタデータ（`st_mtime` / `st_ctime`）からのフォールバック日時判定
  - デフォルト保存ファイル名（`YYYY-MM-DD_vs_相手名.json`）およびJSONメタデータ（`"date"`, `"recorded_at"`）への自動反映
- [x] **Windows タスクバー進捗表示 (`ITaskbarList3`)**
  - 解析中のリアルタイム進捗バー（緑）
  - 一時中断時のステータス表示（黄）
  - エラー時の通知表示（赤）
  - 完了/クリア時の自動リセット
- [x] **選出見せ合い画面 (6on6) 自動検出＆プレビュー・ペア保存機能**
- [x] **動画・スクショ画像群の高速OCR解析＆JSON抽出**
- [x] **ドラッグ＆ドロップ (DnD) 対応・GUIアプリ基盤**

