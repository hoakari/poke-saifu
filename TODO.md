# Poke-Saifu 開発ロードマップ & 課題管理 (Issues)

Poke-Saifu の不具合修正・精度改善および機能拡張タスク一覧です。  
詳細な議論、再現ログ、進捗追跡はすべて [GitHub Issues](https://github.com/hoakari/poke-saifu/issues) にて一元管理しています。

---

## 🐛 既知の不具合・精度改善 (Bug & Accuracy)

| Issue | タイトル | ラベル | 優先度 | 状態 |
| :--- | :--- | :--- | :--- | :--- |
| [#1](https://github.com/hoakari/poke-saifu/issues/1) | [Pipeline/Filter] 技選択UI・固定UI文言のブラックリスト除外および不要ポップアップの破棄 | `bug` `pipeline` `ocr` | **高** | Open |
| [#2](https://github.com/hoakari/poke-saifu/issues/2) | [OCR/Bug] confidence 0.28前後の特定不能な極低信頼度ノイズ行が混入する | `bug` `ocr` | - | **#1 に統合 (Closed)** |
| [#3](https://github.com/hoakari/poke-saifu/issues/3) | [Logic/Bug] 同一メッセージが連続して2〜3回記録される準重複事象（重複排除のすり抜け） | `bug` `accuracy` | **高** | Open |
| [#4](https://github.com/hoakari/poke-saifu/issues/4) | [Logic/Bug] メガシンカ成立メッセージ欠落時のフォールバック推論（ストーン反応イベント連動） | `bug` `logic` `accuracy` | **高** | Open |
| [#5](https://github.com/hoakari/poke-saifu/issues/5) | [Logic/Bug] 多段技・連続処理におけるイベント発生シーケンスの整合ソート | `bug` `logic` | **中** | Open |
| [#6](https://github.com/hoakari/poke-saifu/issues/6) | [Logic/Bug] タイムアウト決着時に終了メッセージ（「〜との勝負に勝った」）が欠落することがある | `bug` `accuracy` | **低 (保留)** | Open |
| [#7](https://github.com/hoakari/poke-saifu/issues/7) | [OCR/Enhancement] 公式マスター辞書（種族名・技・特性・アイテム）を用いたファジーマッチング（レーベンシュタイン距離）の導入 | `enhancement` `ocr` | **高** | Open |
| [#8](https://github.com/hoakari/poke-saifu/issues/8) | [OCR/Discussion] ハングル（韓国語）等の非日本語トレーナー名のOCR崩壊および多言語対応方針 | `ocr` `question` | **要検討 (低)** | Open |

### 課題詳細・対応スコープ
- **[#1](https://github.com/hoakari/poke-saifu/issues/1)**: 「用語の説明 閉じろ」「優先度+1 閉じろ」「バルデアチヤノピオ」などの既知UI固定文字列を正規表現/完全一致でパイプラインから除外。ベンチポケモンのHP確認ポップアップ（`popup` かつ `side: player` の残HP表示等）を盤面イベントから除外、または属性フラグ（`is_bench_ui: true`）を付与して本文イベントと分離。※Issue #2（`confidence < 0.40` の極低信頼度ノイズ自動破棄）を内包して解決。
- **[#4](https://github.com/hoakari/poke-saifu/issues/4)**: 「メガ○○にメガシンカした！」のメッセージ検出がスキップされた場合でも、直前の「○○ナイトと メガリングが 反応した！」を検知していれば、該当ポケモンのメガシンカ状態フラグを成立として補完出力する。
- **[#5](https://github.com/hoakari/poke-saifu/issues/5)**: 多段技ヒット時や追加効果発生時、タイムスタンプが同一秒（または近接秒）内で「瀕死（たおれた）」が「効果抜群/ヒット回数」より先行して記録される現象を、システム固定順（技命中 → 効果判定/急所 → ダメージ/瀕死 → 反動/アイテム発動）に従って自動ソートする。
- **[#7](https://github.com/hoakari/poke-saifu/issues/7)**: 「ブリノユフス → ブリジュラス」「カヒコノ → カビゴン」「フウトホノ → ラウドボーン」「あにひ → おにび」等の典型的なOCR誤読を、類似度スコア（閾値0.75以上等）で自動正規化する辞書ルックアップ層を挟む（LLM負荷軽減と安定化のため優先度「高」へ引き上げ）。

---

## 🚀 新機能・機能拡張 (Features & CI/CD)

| Issue | タイトル | ラベル | 優先度 |
| :--- | :--- | :--- | :--- |
| [#9](https://github.com/hoakari/poke-saifu/issues/9) | [Feature] 選出見せ合い画面（6on6）のOCR解析およびJSON構造化出力 | `feature` `ocr` | 中 |
| [#15](https://github.com/hoakari/poke-saifu/issues/15) | [Pipeline/Feature] 特性「へんげんじざい」等のタイプ変化イベントの構造化出力 | `enhancement` `feature` | 中 |
| [#16](https://github.com/hoakari/poke-saifu/issues/16) | [Vision/Feature] チームプレビュー画面（6on6）からの種族・性別・持ち物アイコンの自動メタデータ抽出 | `feature` `vision` `accuracy` | 中 |
| [#12](https://github.com/hoakari/poke-saifu/issues/12) | [CI/CD] GitHub Actions による Windows 用 exe の自動ビルド＆Releases 配布 | `feature` | 低 |
| [#13](https://github.com/hoakari/poke-saifu/issues/13) | [Feature] GUIアプリ内での最新バージョン確認＆アップデート通知 | `feature` `ui` | 低 |

### 新機能詳細
- **[#15](https://github.com/hoakari/poke-saifu/issues/15)**: マスカーニャやゲッコウガの「へんげんじざい」によるタイプ変化メッセージ（「○○タイプになった！」）を明確なステータス変更イベント（`type: status_change`, `detail: { type_to: "かくとう" }` 等）として構造化し、後続の弱点・耐性判定の文脈フラグとして保持できるようにする。
- **[#16](https://github.com/hoakari/poke-saifu/issues/16)**: プレビュー画面のスクショ/特定フレームから、対戦相手の手持ち6匹の「種族名」「性別（♂/♀/無）」およびプレイヤー側の手持ちを抽出し、JSONのルート直下に `team_preview: { player: [...], opponent: [...] }` として初期出力する機能。

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

