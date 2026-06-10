#!/usr/bin/env python3
"""X 連投スレッド投稿モジュール (aiquant-lab 独自実装)

xpost-community/x_playwright_poster.py が
直接 https://x.com/compose/post に遷移していて 2026-04-28 以降タイムアウトする問題を回避。

このモジュールは:
1. https://x.com/home に遷移
2. SideNav の compose ボタンをクリック
3. textarea に入力
4. 投稿ボタンをクリック

返信ツイートはツイート URL に直接遷移し、Reply ボタン経由で投稿する。

依存: playwright (system python3 にインストール済み前提)
"""

from __future__ import annotations

import json
import time
import sys
from pathlib import Path
from typing import Optional

X_COOKIES_FILE = Path("/home/sol/xpost-community/.x_cookies.json")

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.7390.37 Safari/537.36"
)


def _load_cookies():
    if not X_COOKIES_FILE.exists():
        raise FileNotFoundError(f"X cookies not found: {X_COOKIES_FILE}")
    with open(X_COOKIES_FILE) as f:
        return json.load(f)


def _save_cookies(cookies):
    """投稿成功時にcookieを更新（セッション延長）"""
    with open(X_COOKIES_FILE, "w") as f:
        json.dump(cookies, f, indent=2)


def _new_browser_context(p):
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ],
    )
    ctx = browser.new_context(
        locale="ja-JP",
        user_agent=DEFAULT_UA,
        viewport={"width": 1280, "height": 900},
    )
    ctx.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja', 'en']});
    """
    )
    return browser, ctx


def _open_compose_via_home(page) -> bool:
    """home → SideNav の compose ボタンをクリックしてエディタを開く"""
    page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)  # フィードのレンダリング待ち

    # ログイン確認
    if "login" in page.url.lower() or "flow" in page.url.lower():
        print("  [X] ログインが必要 — cookie 期限切れの可能性")
        return False

    # compose ボタン
    selectors = [
        '[data-testid="SideNav_NewTweet_Button"]',
        'a[href="/compose/post"]',
        '[aria-label*="投稿"][role="link"]',
    ]
    clicked = False
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        print("  [X] compose ボタンが見つかりません")
        return False

    time.sleep(3)

    # textarea が現れるまで待つ
    try:
        page.wait_for_selector(
            '[data-testid="tweetTextarea_0"]',
            state="visible",
            timeout=15000,
        )
    except Exception:
        print("  [X] textarea が出現せず")
        return False

    return True


def _type_and_submit(page, text: str) -> str | None:
    """textarea に入力し投稿ボタンをクリック → tweet_id (or success token)"""
    try:
        ta = page.locator('[data-testid="tweetTextarea_0"]').first
        ta.click()
        time.sleep(0.5)
        # 文字単位入力で改行・特殊文字を確実にする
        page.keyboard.type(text, delay=10)
        time.sleep(2)
    except Exception as e:
        print(f"  [X] 入力失敗: {e}")
        return None

    # 投稿ボタンを JS で直接クリック (Playwright の disabled 判定を回避)
    submitted = page.evaluate(
        """() => {
            const ids = ['tweetButton', 'tweetButtonInline'];
            for (const id of ids) {
                const btn = document.querySelector(`[data-testid="${id}"]`);
                if (btn) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }"""
    )

    if not submitted:
        print("  [X] 投稿ボタンが押せませんでした (DOM evaluate)")
        return None

    # 投稿完了の検知（モーダルが閉じる or タイムラインに反映される）
    time.sleep(6)

    # 1) URL から tweet_id を取得（詳細ページに遷移した場合）
    if "/status/" in page.url:
        tid = page.url.rstrip("/").split("/status/")[-1].split("?")[0]
        return tid

    # 2) compose モーダルが閉じたか確認（DOM 上から消える）
    closed = page.evaluate(
        """() => !document.querySelector('[data-testid="tweetTextarea_0"]')"""
    )
    if not closed:
        # textarea が空になっているなら投稿は走った可能性が高い
        empty = page.evaluate(
            """() => {
                const t = document.querySelector('[data-testid="tweetTextarea_0"]');
                return t ? !t.innerText.trim() : true;
            }"""
        )
        if not empty:
            print("  [X] モーダルがまだ開いていて入力も残っている = 失敗")
            return None

    # 3) 自分のプロフィールを確認して直近自分の投稿を取得
    #    text snippet で本文一致を探す。固定ツイートは除外。
    try:
        me = page.evaluate(
            """() => {
                const link = document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                return link ? link.getAttribute('href').replace(/^\\//, '') : null;
            }"""
        )
        if me:
            page.goto(f"https://x.com/{me}", wait_until="domcontentloaded", timeout=20000)
            time.sleep(4)
            latest = page.evaluate(
                """(snippet) => {
                    const pinned_markers = ["Pinned", "固定", "ピン留めされた"];
                    const articles = document.querySelectorAll('article');
                    for (const a of Array.from(articles).slice(0, 8)) {
                        const txt = a.innerText || '';
                        const isPinned = pinned_markers.some(m => txt.startsWith(m + '\\n') || txt.includes('\\n' + m + '\\n'));
                        if (isPinned) continue;
                        if (txt.includes(snippet)) {
                            const link = a.querySelector('a[href*="/status/"]');
                            return link ? link.getAttribute('href') : 'matched';
                        }
                    }
                    return null;
                }""",
                text[:30].replace("\n", " "),
            )
            if latest and "/status/" in latest:
                return latest.rstrip("/").split("/status/")[-1].split("?")[0]
            if latest == "matched":
                return "playwright_success"
    except Exception:
        pass

    # 4) どれも判定できなかったら success token を返す
    return "playwright_success"


def _navigate_to_reply(page, reply_to_id: str) -> bool:
    """指定ツイートに遷移し Reply 入力エリアを開く"""
    page.goto(
        f"https://x.com/i/web/status/{reply_to_id}",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    time.sleep(4)

    # 返信入力エリア (詳細ページでは常に表示)
    try:
        page.wait_for_selector(
            '[data-testid="tweetTextarea_0"]',
            state="visible",
            timeout=15000,
        )
        return True
    except Exception:
        # Replyボタンを探してクリック
        try:
            reply_btn = page.locator('[data-testid="reply"]').first
            reply_btn.click(timeout=5000)
            page.wait_for_selector(
                '[data-testid="tweetTextarea_0"]',
                state="visible",
                timeout=10000,
            )
            return True
        except Exception:
            return False


def post_tweet(text: str, reply_to: str | None = None) -> str | None:
    """ツイート1件を投稿。reply_to があれば返信として投稿。

    Returns:
        tweet_id 文字列 or "playwright_success" or None (失敗)
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [X] playwright 未インストール (system python3)")
        return None

    cookies = _load_cookies()

    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        try:
            if reply_to:
                ok = _navigate_to_reply(page, reply_to)
            else:
                ok = _open_compose_via_home(page)

            if not ok:
                return None

            tid = _type_and_submit(page, text)

            # 成功時は cookie 保存 (セッション延長)
            if tid:
                try:
                    _save_cookies(ctx.cookies())
                except Exception:
                    pass

            return tid
        finally:
            try:
                browser.close()
            except Exception:
                pass


def _is_pinned_article(article_html_text: str) -> bool:
    """記事テキストに固定ツイートマーカーが含まれるか判定"""
    pinned_markers = ["Pinned", "固定", "ピン留めされた"]
    return any(m in article_html_text for m in pinned_markers)


def _get_latest_user_tweet_id(page) -> Optional[str]:
    """自分のプロフィールから直近自分のツイート ID を取得（固定ツイートはスキップ）

    Bug fix (2026-04-30): 以前は articles の先頭を取っていたため、
    固定ツイート (2025-11-12 ID 1988568030847336795) を Episode 1 の
    thread_id として誤記録していた。固定マーカーを検出して除外する。
    """
    try:
        me = page.evaluate(
            """() => {
                const link = document.querySelector('[data-testid="AppTabBar_Profile_Link"]');
                return link ? link.getAttribute('href').replace(/^\\//, '') : null;
            }"""
        )
        if not me:
            return None
        page.goto(f"https://x.com/{me}", wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        # 固定ツイートをスキップしつつ、最も新しい(=time が最大)のものを取得
        latest = page.evaluate(
            """() => {
                const pinned_markers = ["Pinned", "固定", "ピン留めされた"];
                const candidates = [];
                const articles = document.querySelectorAll('article');
                for (const a of Array.from(articles).slice(0, 8)) {
                    const link = a.querySelector('a[href*="/status/"]');
                    if (!link) continue;
                    const txt = a.innerText || '';
                    // socialContext に「固定」「Pinned」が含まれるか
                    const isPinned = pinned_markers.some(m => txt.startsWith(m + '\\n') || txt.includes('\\n' + m + '\\n'));
                    if (isPinned) continue;
                    const time_el = a.querySelector('time');
                    const ts = time_el ? time_el.getAttribute('datetime') : '';
                    candidates.push({ href: link.getAttribute('href'), ts });
                }
                if (candidates.length === 0) return null;
                // 最新 (ts 降順) を返す
                candidates.sort((a, b) => b.ts.localeCompare(a.ts));
                return candidates[0].href;
            }"""
        )
        if latest and "/status/" in latest:
            return latest.rstrip("/").split("/status/")[-1].split("?")[0]
    except Exception:
        pass
    return None


def post_thread(tweets: list[str], pause_seconds: int = 6) -> dict:
    """連投スレッドを投稿（連鎖型: 各ツイートが前のツイートへの返信）

    Returns:
        {
            "thread_id": str | None,         # 1ツイート目の ID
            "results": [{"index": int, "tweet_id": str}],
            "success": bool,
        }
    """
    if not tweets:
        return {"thread_id": None, "results": [], "success": False}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [X] playwright 未インストール (system python3)")
        return {"thread_id": None, "results": [], "success": False, "failed_at": 0}

    cookies = _load_cookies()
    thread_id = None
    reply_to = None
    results = []

    # 全ツイートを 1 つの browser session で連投する
    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        try:
            for i, tweet in enumerate(tweets):
                print(f"  [X] {i+1}/{len(tweets)} ({len(tweet)}文字) 投稿中...")

                if reply_to is None:
                    # 1 ツイート目: home → compose
                    if not _open_compose_via_home(page):
                        results.append({"index": i, "tweet_id": None})
                        return {
                            "thread_id": thread_id,
                            "results": results,
                            "success": False,
                            "failed_at": i,
                        }
                else:
                    # 2 ツイート目以降: 前のツイート詳細ページ → 返信エリア
                    if not _navigate_to_reply(page, reply_to):
                        results.append({"index": i, "tweet_id": None})
                        return {
                            "thread_id": thread_id,
                            "results": results,
                            "success": False,
                            "failed_at": i,
                        }

                tid = _type_and_submit(page, tweet)
                if not tid:
                    results.append({"index": i, "tweet_id": None})
                    return {
                        "thread_id": thread_id,
                        "results": results,
                        "success": False,
                        "failed_at": i,
                    }

                # tid が "playwright_success" の場合、直近自分のツイート ID を取得
                if tid == "playwright_success":
                    tid = _get_latest_user_tweet_id(page) or tid

                results.append({"index": i, "tweet_id": tid})
                if i == 0 and tid != "playwright_success":
                    thread_id = tid
                if tid != "playwright_success":
                    reply_to = tid

                if i < len(tweets) - 1:
                    time.sleep(pause_seconds)

            # cookie セーブ
            try:
                _save_cookies(ctx.cookies())
            except Exception:
                pass

            return {"thread_id": thread_id, "results": results, "success": True}
        finally:
            try:
                browser.close()
            except Exception:
                pass


def cli():
    """CLI: stdin から JSON で tweets を受け取り投稿、結果を JSON で stdout"""
    payload = json.loads(sys.stdin.read())
    tweets = payload["tweets"] if isinstance(payload, dict) else payload
    pause = payload.get("pause", 6) if isinstance(payload, dict) else 6
    result = post_thread(tweets, pause_seconds=pause)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    cli()
