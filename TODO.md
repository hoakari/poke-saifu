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
| [#10](https://github.com/hoakari/poke-saifu/issues/10) | [Feature] 複数動画のキュー登録・連続自動解析（バッチ処理・完了通知音） | `feature` `ui` |
| [#11](https://github.com/hoakari/poke-saifu/issues/11) | [Feature] 解析完了時の指定フォルダへの自動保存（Auto-Save） | `feature` `ui` |
| [#12](https://github.com/hoakari/poke-saifu/issues/12) | [CI/CD] GitHub Actions による Windows 用 exe の自動ビルド＆Releases 配布 | `feature` |
| [#13](https://github.com/hoakari/poke-saifu/issues/13) | [Feature] GUIアプリ内での最新バージョン確認＆アップデート通知 | `feature` `ui` |

---

## 📅 完了済みタスク (Done)

- [x] **Windows タスクバー進捗表示 (`ITaskbarList3`)**
  - 解析中のリアルタイム進捗バー（緑）
  - 一時中断時のステータス表示（黄）
  - エラー時の通知表示（赤）
  - 完了/クリア時の自動リセット
- [x] **選出見せ合い画面 (6on6) 自動検出＆プレビュー・ペア保存機能**
- [x] **動画・スクショ画像群の高速OCR解析＆JSON抽出**
- [x] **ドラッグ＆ドロップ (DnD) 対応・GUIアプリ基盤**
