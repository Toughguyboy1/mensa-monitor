# MENSA 受験情報通知アプリ

JAPAN MENSA の受験申し込みページ (https://mensa.jp/exam/) を
**5分ごと** に自動チェックし、変更があれば **iPhone に即時プッシュ通知** します。

## 仕組み

- **GitHub Actions** が5分おきに Python スクリプト (`monitor.py`) を実行
- ページ本文を取得してハッシュ化し、前回分 (`state.hash` / `state.txt`) と比較
- 差分があれば **Pushover** 経由で iPhone にプッシュ通知
- サーバー不要・完全無料（パブリックリポジトリの場合）

## セットアップ手順

セットアップの完全な手順は **`セットアップ手順書.docx`** を参照してください。
アカウント作成から動作確認まで、画面操作を一つずつ解説しています。

概要だけを記すと以下の通りです。

1. GitHub アカウントを作成
2. Pushover アカウントを作成し、iPhone アプリをインストール
3. このフォルダの中身を新規リポジトリにアップロード
4. GitHub リポジトリの Settings → Secrets に `PUSHOVER_TOKEN` と `PUSHOVER_USER` を登録
5. Actions タブから "MENSA Exam Page Monitor" を手動実行してテスト

## ファイル構成

| ファイル | 役割 |
|---|---|
| `monitor.py` | 監視本体（Python） |
| `requirements.txt` | Python の依存ライブラリ |
| `.github/workflows/monitor.yml` | GitHub Actions 設定（5分ごと実行） |
| `state.txt` / `state.hash` | 前回取得分（自動生成、手で触らない） |
| `セットアップ手順書.docx` | 初心者向けの完全セットアップガイド |

## カスタマイズ

- **監視対象URLを変える**: リポジトリの Settings → Variables に `TARGET_URL` を追加
- **頻度を変える**: `.github/workflows/monitor.yml` の `cron` を編集
  - 例）`*/15 * * * *` で15分毎、`0 * * * *` で1時間毎
- **通知音や優先度を変える**: `monitor.py` の `send_pushover` 内、`priority` / `sound` を編集
