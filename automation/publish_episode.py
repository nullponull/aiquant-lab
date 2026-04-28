#!/usr/bin/env python3
"""連載「AIで投資の壁を越える」自動投稿スクリプト

state.json に基づき、次に投稿すべきエピソードを判定し、
1. note (AIコンパス) に記事投稿 (note-post-mcp/publish-single.cjs 経由)
2. X (ぬるぽん) に告知スレッド投稿 (xpost-community 経由)

の 2 つを実行する。

使い方:
    python3 publish_episode.py [--dry-run] [--episode N] [--no-x] [--no-note]

systemd timer / cron で定期実行する想定。
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "automation" / "state.json"

# AIコンパス用 note 認証 state
NOTE_STATE_PATH = Path("/home/sol/.note-state-aicompass3.json")

# 既存の note 投稿スクリプト (Node.js + Playwright)
NOTE_PUBLISHER_CJS = Path("/home/sol/note-post-mcp/publish-single.cjs")

# xpost-community のディレクトリ (subprocess で python3 実行)
XPOST_DIR = Path("/home/sol/xpost-community")

# 連載共通タグ
SERIES_TAGS = [
    "AI",
    "投資",
    "AIエージェント",
    "クオンツ",
    "バックテスト",
    "ClaudeCode",
    "資産運用",
    "金融",
    "データサイエンス",
]

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


def build_article_with_frontmatter(article_path: Path, episode: dict) -> str:
    """publish-single.cjs が読めるフロントマター付き markdown を生成"""
    body = article_path.read_text(encoding="utf-8")

    # 本文先頭の「# タイトル」行を削る (note 側で title が別管理になるので)
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        # タイトル直後の空行も削除
        while lines and lines[0].strip() == "":
            lines.pop(0)
    cleaned_body = "\n".join(lines)

    # フロントマター + 本文
    title = episode["title"]
    tag_lines = "\n".join(f"  - {t}" for t in SERIES_TAGS)
    frontmatter = f"""---
title: "{title}"
tags:
{tag_lines}
---

"""
    return frontmatter + cleaned_body


def publish_to_note(article_path: Path, episode: dict, dry_run: bool = False) -> dict:
    """note.com に記事を投稿 (publish-single.cjs 経由)"""
    article_path = article_path.resolve()
    if not article_path.exists():
        return {"success": False, "url": None, "error": f"Article not found: {article_path}"}

    if not NOTE_STATE_PATH.exists():
        return {"success": False, "url": None, "error": f"note auth not found: {NOTE_STATE_PATH}"}

    if not NOTE_PUBLISHER_CJS.exists():
        return {"success": False, "url": None, "error": f"publisher not found: {NOTE_PUBLISHER_CJS}"}

    # フロントマター付き一時ファイル作成
    full_content = build_article_with_frontmatter(article_path, episode)

    if dry_run:
        logger.info(f"[DRY RUN] note publish: {article_path}")
        logger.info(f"  Title: {episode['title']}")
        logger.info(f"  Body length: {len(full_content)} chars")
        return {"success": True, "url": "https://note.com/dry-run", "error": None}

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmpf:
        tmpf.write(full_content)
        tmp_path = tmpf.name

    try:
        env = os.environ.copy()
        env["NOTE_POST_STATE_PATH"] = str(NOTE_STATE_PATH)
        # Node を確実に見つける
        node_paths = [
            "/home/sol/.nvm/versions/node/v22.17.0/bin",
            "/usr/local/bin",
            "/usr/bin",
        ]
        env["PATH"] = ":".join(node_paths) + ":" + env.get("PATH", "")

        node_bin = "node"
        for p in node_paths:
            if (Path(p) / "node").exists():
                node_bin = str(Path(p) / "node")
                break

        logger.info(f"note 投稿開始: {article_path.name} (price=0)")
        result = subprocess.run(
            [node_bin, str(NOTE_PUBLISHER_CJS), tmp_path, "0"],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "url": None, "error": "publisher timeout (10 min)"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    logger.info(f"note publish stdout (last 500): {result.stdout[-500:] if result.stdout else '(none)'}")
    if result.stderr:
        logger.info(f"note publish stderr (last 300): {result.stderr[-300:]}")

    # SUCCESS: <url> を抽出
    success_match = re.search(r"SUCCESS:\s*(https?://\S+)", output)
    if success_match:
        url = success_match.group(1).rstrip(")")
        return {"success": True, "url": url, "error": None}

    # 失敗判定
    return {
        "success": False,
        "url": None,
        "error": f"Exit {result.returncode}, no SUCCESS marker. Output tail: {output[-300:]}",
    }


def parse_x_thread(promo_path: Path) -> list[str]:
    """X promo ファイルから「メイン告知ツイート（連投スレッド）」のツイートを抽出"""
    text = promo_path.read_text(encoding="utf-8")

    main_section_match = re.search(
        r"##\s*メイン告知ツイート.*?(?=\n##\s*[^#])", text, re.DOTALL
    )
    if not main_section_match:
        logger.warning("メイン告知ツイートセクションが見つかりません")
        return []
    section = main_section_match.group(0)

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
    """X に連投スレッドを投稿 (aiquant-lab/automation/x_poster.py 経由)

    注: xpost-community/x_playwright_poster.py は 2026-04 以降、
    https://x.com/compose/post 直リンクで Timeout する問題があるため、
    aiquant-lab 独自の home → SideNav 経由実装を使う。
    """
    if not tweets:
        return {"success": False, "thread_id": None, "error": "No tweets"}

    if dry_run:
        logger.info(f"[DRY RUN] X thread ({len(tweets)} tweets):")
        for i, t in enumerate(tweets[:3], 1):
            logger.info(f"  [{i}] {t[:80]}...")
        return {"success": True, "thread_id": "dry-run-thread", "error": None}

    # /usr/bin/python3 を明示（playwright が system python にインストールされているため）
    system_python = "/usr/bin/python3"
    if not Path(system_python).exists():
        system_python = "python3"

    x_poster_script = PROJECT_ROOT / "automation" / "x_poster.py"

    try:
        result = subprocess.run(
            [system_python, str(x_poster_script)],
            input=json.dumps({"tweets": tweets, "pause": 7}),
            capture_output=True,
            text=True,
            timeout=900,  # 15分（10ツイートでも余裕）
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "thread_id": None, "error": "X poster timeout"}

    logger.info(f"X poster stdout: {result.stdout[-500:]}")
    if result.stderr:
        logger.warning(f"X poster stderr: {result.stderr[-300:]}")

    # x_poster は最後の行に JSON を出力
    last_json_line = None
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last_json_line = line
            break

    if not last_json_line:
        return {
            "success": False,
            "thread_id": None,
            "error": f"no JSON output. Exit {result.returncode}, stderr: {result.stderr[-200:]}",
        }

    try:
        data = json.loads(last_json_line)
        return {
            "success": data.get("success", False),
            "thread_id": data.get("thread_id"),
            "error": None if data.get("success") else f"failed_at={data.get('failed_at')}",
            "results": data.get("results", []),
        }
    except json.JSONDecodeError as e:
        return {"success": False, "thread_id": None, "error": f"parse error: {e}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--episode", type=int)
    parser.add_argument("--no-x", action="store_true")
    parser.add_argument("--no-note", action="store_true")
    args = parser.parse_args()

    state = load_state()
    episode = find_next_episode(state, args.episode)

    if not episode:
        logger.info("投稿すべきエピソードがありません")
        return 0

    logger.info(f"=== Episode #{episode['number']}: {episode['title'][:60]} ===")

    note_ok = True
    x_ok = True

    # 1. note 投稿
    if not args.no_note:
        article_path = PROJECT_ROOT / episode["article_path"]
        result = publish_to_note(article_path, episode, dry_run=args.dry_run)
        if result["success"]:
            episode["note_url"] = result["url"]
            logger.info(f"✓ note 投稿成功: {result['url']}")
        else:
            note_ok = False
            logger.error(f"✗ note 投稿失敗: {result['error']}")
    else:
        logger.info("note 投稿はスキップ")

    # 2. X スレッド投稿
    if not args.no_x and note_ok:  # note 失敗時は X もスキップ (URL がないため)
        promo_path = PROJECT_ROOT / episode["x_promo_path"]
        if not promo_path.exists():
            logger.warning(f"X promo ファイルなし: {promo_path}")
            x_ok = False
        else:
            raw_tweets = parse_x_thread(promo_path)
            tweets = replace_placeholders(raw_tweets, episode)
            logger.info(f"X スレッド: {len(tweets)} ツイート")

            result = post_x_thread(tweets, dry_run=args.dry_run)
            if result["success"]:
                episode["x_thread_id"] = result["thread_id"]
                logger.info(f"✓ X 投稿成功: thread_id={result['thread_id']}")
            else:
                x_ok = False
                # 部分成功の場合は thread_id を残す
                if result.get("thread_id"):
                    episode["x_thread_id"] = result["thread_id"]
                logger.error(f"✗ X 投稿失敗: {result['error']}")
    elif not note_ok:
        logger.warning("note 失敗のため X もスキップ")
    else:
        logger.info("X 投稿はスキップ")

    # 3. state 更新 (両方成功時のみ published=true)
    if not args.dry_run:
        if note_ok and x_ok:
            episode["published"] = True
            episode["published_at"] = datetime.now(JST).isoformat()
            state["last_published_episode"] = episode["number"]
            save_state(state)
            logger.info(f"✓ Episode {episode['number']} 完全公開")
            return 0
        else:
            # 部分成功 (URL 取得済みなど) も保存
            save_state(state)
            logger.error(f"✗ Episode {episode['number']} 不完全 (note={note_ok}, x={x_ok})")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
