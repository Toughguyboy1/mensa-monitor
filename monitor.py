#!/usr/bin/env python3
"""
JAPAN MENSA 受験情報 監視スクリプト
--------------------------------
https://mensa.jp/exam/ のページ内容を取得し、
前回からの変更があれば Pushover で iPhone に通知します。

環境変数:
  PUSHOVER_TOKEN - Pushover のアプリケーショントークン
  PUSHOVER_USER  - Pushover のユーザーキー
  TARGET_URL     - 監視対象のURL (省略時は https://mensa.jp/exam/)
"""

from __future__ import annotations

import difflib
import hashlib
import os
import pathlib
import re
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# 設定
# --------------------------------------------------------------------------- #
TARGET_URL = os.environ.get("TARGET_URL", "https://mensa.jp/exam/")
STATE_FILE = pathlib.Path("state.txt")
HASH_FILE = pathlib.Path("state.hash")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
PUSHOVER_API = "https://api.pushover.net/1/messages.json"
JST = timezone(timedelta(hours=9))


# --------------------------------------------------------------------------- #
# ページ取得 + 正規化
# --------------------------------------------------------------------------- #
def fetch_page(url: str) -> str:
    """URL からHTMLを取得する。"""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    # 文字化け対策: apparent_encoding を優先
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def normalize(html: str) -> str:
    """
    HTML から本文テキストだけを抽出し、比較に関係ないノイズを除去する。
    - <script>/<style>/<noscript> を除去
    - 空白・改行を正規化
    - 日付・時刻っぽい表記を除去（更新日時などの誤検知を避ける）
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "meta", "link"]):
        tag.decompose()

    # body が取れれば body だけに絞る（ヘッダー/フッター以外のコンテンツに注力）
    body = soup.body or soup
    text = body.get_text(separator="\n")

    # 連続する空白・改行を正規化
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    # 自動更新されがちな時刻表記を除去 (HH:MM, YYYY-MM-DD HH:MM:SS 等)
    text = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2})?\b", "", text)
    text = re.sub(r"\b\d{1,2}:\d{2}:\d{2}\b", "", text)

    return text.strip()


# --------------------------------------------------------------------------- #
# 差分検知
# --------------------------------------------------------------------------- #
def load_previous() -> tuple[str, str]:
    """前回の本文とハッシュを読み込む。無ければ空文字。"""
    prev_text = STATE_FILE.read_text(encoding="utf-8") if STATE_FILE.exists() else ""
    prev_hash = HASH_FILE.read_text(encoding="utf-8").strip() if HASH_FILE.exists() else ""
    return prev_text, prev_hash


def save_current(text: str, digest: str) -> None:
    STATE_FILE.write_text(text, encoding="utf-8")
    HASH_FILE.write_text(digest, encoding="utf-8")


def make_diff_snippet(prev: str, curr: str, max_lines: int = 15) -> str:
    """人間に読みやすい差分スニペットを作る。"""
    diff = difflib.unified_diff(
        prev.splitlines(),
        curr.splitlines(),
        lineterm="",
        n=1,
    )
    changed: list[str] = []
    for line in diff:
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+") or line.startswith("-"):
            changed.append(line)
        if len(changed) >= max_lines:
            changed.append("... (以下省略) ...")
            break
    return "\n".join(changed) if changed else "(差分詳細を取得できませんでした)"


# --------------------------------------------------------------------------- #
# Pushover 通知
# --------------------------------------------------------------------------- #
def send_pushover(title: str, message: str, url: str) -> None:
    token = os.environ.get("PUSHOVER_TOKEN")
    user = os.environ.get("PUSHOVER_USER")
    if not token or not user:
        print("[警告] PUSHOVER_TOKEN / PUSHOVER_USER が未設定のため通知をスキップします。")
        return

    # Pushover の message 上限は 1024 文字
    if len(message) > 1000:
        message = message[:1000] + "\n...(省略)"

    payload = {
        "token": token,
        "user": user,
        "title": title,
        "message": message,
        "url": url,
        "url_title": "MENSA受験情報ページを開く",
        "priority": 1,  # 0=通常, 1=高優先度 (通知音強制)
        "sound": "pushover",
    }
    resp = requests.post(PUSHOVER_API, data=payload, timeout=30)
    if resp.status_code != 200:
        print(f"[エラー] Pushover 通知失敗: {resp.status_code} {resp.text}")
        resp.raise_for_status()
    print("[OK] Pushover 通知を送信しました。")


# --------------------------------------------------------------------------- #
# メイン
# --------------------------------------------------------------------------- #
def main() -> int:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    print(f"=== 監視実行: {now} ===")
    print(f"対象URL: {TARGET_URL}")

    try:
        html = fetch_page(TARGET_URL)
    except Exception as e:
        print(f"[エラー] ページ取得失敗: {e}")
        # 取得失敗だけでは通知しない（連続失敗時のみ後続で拡張可）
        return 1

    current_text = normalize(html)
    current_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
    prev_text, prev_hash = load_previous()

    if not prev_hash:
        # 初回実行: 通知せずに状態を保存
        save_current(current_text, current_hash)
        print("[初回] 現在の状態を保存しました。次回以降、変更を検知したら通知します。")
        return 0

    if current_hash == prev_hash:
        print("[変更なし] スキップ。")
        return 0

    # 変更あり → 通知
    diff_snippet = make_diff_snippet(prev_text, current_text)
    title = "MENSA受験情報が更新されました"
    message = (
        f"検知時刻: {now}\n"
        f"URL: {TARGET_URL}\n\n"
        f"--- 変更差分（抜粋）---\n{diff_snippet}"
    )
    print("[変更検知] 通知を送信します。")
    print(message)

    try:
        send_pushover(title, message, TARGET_URL)
    except Exception as e:
        print(f"[エラー] 通知送信中に例外: {e}")
        # 通知に失敗しても state は更新しない（次回再試行）
        return 2

    save_current(current_text, current_hash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
