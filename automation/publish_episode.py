#!/usr/bin/env python3
"""連載「AIで投資の壁を越える」自動投稿スクリプト

state.json に基づき、次に投稿すべきエピソードを判定し、
1. note (AIコンパス) に記事投稿
2. X (ぬるぽん) に告知スレッド投稿

の 2 つを実行する。

使い方:
    python3 publish_episode.py [--dry-run] [--episode N] [--no-x] [--no-note]

systemd timer / cron で定期実行する想定。
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "automation" / "state.json"
NOTE_STATE_PATH = Path.home() / ".note-state.json"

# 既存 X 投稿モジュールのパス
XPOST_SCRIPTS = Path("/home/sol/xpost-community/scripts")
sys.path.insert(0, str(XPOST_SCRIPTS))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("aiquant-publisher")


def load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def find_next_episode(state: dict, force_episode: int | None = None) -> dict | None:
    """次に投稿すべきエピソードを返す"""
    if force_episode is not None:
        for ep in state["episodes"]:
            if ep["number"] == force_episode:
                return ep
        return None

    now = datetime.now(JST)
    for ep in state["episodes"]:
        if ep["published"]:
            continue
        scheduled = datetime.fromisoformat(ep["scheduled_for"])
        if now >= scheduled:
            return ep
    return None


def publish_to_note(article_path: Path, dry_run: bool = False) -> dict:
    """note.com に記事を投稿（既存 daily-note-post の仕組みを踏襲）"""
    article_path = article_path.resolve()
    if not article_path.exists():
        return {"success": False, "url": None, "error": f"Article not found: {article_path}"}

    if not NOTE_STATE_PATH.exists():
        return {"success": False, "url": None, "error": f"note auth not found: {NOTE_STATE_PATH}"}

    if dry_run:
        logger.info(f"[DRY RUN] note publish: {article_path}")
        return {"success": True, "url": "https://note.com/dry-run", "error": None}

    prompt = f'''以下のMCPツールを実行してください:

mcp__note-post__publish_note(
    markdown_path="{article_path}",
    state_path="{NOTE_STATE_PATH}"
)

投稿が完了したら、投稿されたURLだけを返してください。他の説明は不要です。'''

    logger.info(f"note 投稿開始: {article_path.name}")
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "url": None, "error": "Claude CLI timeout (10 min)"}

    output = result.stdout.strip()
    logger.info(f"note publish stdout (last 300): {output[-300:]}")

    url_patterns = [
        r"https://note\.com/[^\s\)\"\']+",
        r"https://editor\.note\.com/[^\s\)\"\']+",
    ]
    url = None
    for pattern in url_patterns:
        matches = re.findall(pattern, output)
        if matches:
            url = matches[0].rstrip(")")
            break

    if url:
        return {"success": True, "url": url, "error": None}
    if result.returncode == 0:
        return {"success": True, "url": None, "error": None}
    return {
        "success": False,
        "url": None,
        "error": f"Exit {result.returncode}: {output[:200]}",
    }


def parse_x_thread(promo_path: Path) -> list[str]:
    """X promo ファイルから「メイン告知ツイート（連投スレッド）」セクションを抽出

    形式: ### Tweet N（...）の下にある最初のコードブロックをツイート本文として抽出
    """
    text = promo_path.read_text(encoding="utf-8")

    # 「メイン告知ツイート」セクションのみ対象
    main_section_match = re.search(
        r"##\s*メイン告知ツイート.*?(?=\n##\s*[^#])", text, re.DOTALL
    )
    if not main_section_match:
        logger.warning("メイン告知ツイートセクションが見つかりません")
        return []

    section = main_section_match.group(0)

    # ### Tweet N から次の ### Tweet または ## までの間のコードブロックを抽出
    tweet_pattern = re.compile(
        r"###\s*Tweet\s*\d+.*?```(?:\w*\n)?(.*?)```", re.DOTALL
    )
    tweets = []
    for m in tweet_pattern.finditer(section):
        tweet = m.group(1).strip()
        if tweet:
            tweets.append(tweet)

    return tweets


def replace_placeholders(tweets: list[str], episode: dict) -> list[str]:
    """ツイート内のプレースホルダーを実 URL に置換"""
    note_url = episode.get("note_url") or ""
    out = []
    for t in tweets:
        t = t.replace("[note URL]", note_url)
        t = t.replace("[GitHub URL]", "https://github.com/nullponull/aiquant-lab")
        t = t.replace("[GitHubURL]", "https://github.com/nullponull/aiquant-lab")
        t = t.replace("[マニフェストURL]", note_url)
        out.append(t)
    return out


def post_x_thread(tweets: list[str], dry_run: bool = False) -> dict:
    """X に連投スレッドを投稿"""
    if not tweets:
        return {"success": False, "thread_id": None, "error": "No tweets to post"}

    if dry_run:
        logger.info(f"[DRY RUN] X thread ({len(tweets)} tweets):")
        for i, t in enumerate(tweets[:3], 1):
            logger.info(f"  [{i}] {t[:80]}...")
        return {"success": True, "thread_id": "dry-run-thread", "error": None}

    try:
        from x_playwright_poster import post_tweet_via_playwright
    except ImportError as e:
        return {"success": False, "thread_id": None, "error": f"X poster import: {e}"}

    thread_id = None
    reply_to = None
    for i, tweet in enumerate(tweets):
        logger.info(f"X 投稿 {i+1}/{len(tweets)} ({len(tweet)}文字)")
        tweet_id = post_tweet_via_playwright(tweet, reply_to=reply_to)
        if not tweet_id:
            return {
                "success": False,
                "thread_id": thread_id,
                "error": f"Tweet {i+1} failed",
            }
        if i == 0:
            thread_id = tweet_id
        reply_to = tweet_id
        # スレッドの間隔（連投制限回避）
        if i < len(tweets) - 1:
            time.sleep(5)

    return {"success": True, "thread_id": thread_id, "error": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="実投稿せず処理だけ")
    parser.add_argument("--episode", type=int, help="特定エピソードを強制投稿")
    parser.add_argument("--no-x", action="store_true", help="X 投稿スキップ")
    parser.add_argument("--no-note", action="store_true", help="note 投稿スキップ")
    args = parser.parse_args()

    state = load_state()
    episode = find_next_episode(state, args.episode)

    if not episode:
        logger.info("投稿すべきエピソードがありません")
        return 0

    logger.info(f"=== Episode #{episode['number']}: {episode['title'][:60]} ===")

    # 1. note 投稿
    if not args.no_note:
        article_path = PROJECT_ROOT / episode["article_path"]
        result = publish_to_note(article_path, dry_run=args.dry_run)
        if not result["success"]:
            logger.error(f"note 投稿失敗: {result['error']}")
            return 1
        episode["note_url"] = result["url"]
        logger.info(f"note 投稿成功: {result['url']}")
    else:
        logger.info("note 投稿はスキップ")

    # 2. X スレッド投稿
    if not args.no_x:
        promo_path = PROJECT_ROOT / episode["x_promo_path"]
        if not promo_path.exists():
            logger.warning(f"X promo ファイルなし: {promo_path}")
        else:
            raw_tweets = parse_x_thread(promo_path)
            tweets = replace_placeholders(raw_tweets, episode)
            logger.info(f"X スレッド: {len(tweets)} ツイート")

            result = post_x_thread(tweets, dry_run=args.dry_run)
            if result["success"]:
                episode["x_thread_id"] = result["thread_id"]
                logger.info(f"X 投稿成功: thread_id={result['thread_id']}")
            else:
                logger.error(f"X 投稿失敗: {result['error']}")
    else:
        logger.info("X 投稿はスキップ")

    # 3. state 更新
    if not args.dry_run:
        episode["published"] = True
        episode["published_at"] = datetime.now(JST).isoformat()
        state["last_published_episode"] = episode["number"]
        save_state(state)
        logger.info(f"state 更新: episode {episode['number']} を published に")

    return 0


if __name__ == "__main__":
    sys.exit(main())
