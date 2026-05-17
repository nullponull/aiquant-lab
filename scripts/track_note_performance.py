#!/usr/bin/env python3
"""note記事の効果計測（PV/購入数/コメント等）

公開後の記事を定期スクレイピング + ダッシュボード化。
2026-05-17 公開: 番外編「第7の壁」(¥3,000) を主対象。

【使い方】
# 単発実行
python3 /home/sol/aiquant-lab/scripts/track_note_performance.py

# cron で1時間毎
0 * * * * /home/sol/aiquant-lab/scripts/track_note_performance.py >> /tmp/note_perf.log 2>&1

【出力】
- /home/sol/aiquant-lab/data/note_performance.csv (時系列ログ)
- 標準出力にサマリ
"""
import csv
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# 計測対象記事
TARGETS = [
    {
        'id': '005_bangai',
        'title': '番外編「第7の壁」',
        'url': 'https://note.com/ai_compass_media/n/n73cb83517fd3',
        'price': 3000,
        'published_at': '2026-05-17',
    },
    # 連載過去回（基準比較用）
    {
        'id': '001_3weeks',
        'title': '#1 3週間+4%',
        'url': 'https://note.com/ai_compass_media',  # 個別URLは公開後に更新
        'price': 0,  # 無料
    },
]

OUTPUT_DIR = Path('/home/sol/aiquant-lab/data')
OUTPUT_CSV = OUTPUT_DIR / 'note_performance.csv'


def fetch_note_html(url: str) -> str:
    """noteの記事HTMLを取得（公開部分のみ）"""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; aiquant-tracker/1.0; +https://ai-media.co.jp)',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠ fetch error: {e}", file=sys.stderr)
        return ''


def extract_metrics(html: str) -> dict:
    """note ページから可視メトリクスを抽出

    取得可能項目:
    - スキ数 (like_count)
    - コメント数 (comment_count)
    - 想定読了時間
    - JSON-LD の publish date
    - meta description
    """
    metrics = {}
    # スキ数 (data-likeCount や aria-label から)
    m = re.search(r'"likeCount"\s*:\s*(\d+)', html)
    if m:
        metrics['like_count'] = int(m.group(1))

    # コメント数
    m = re.search(r'"commentCount"\s*:\s*(\d+)', html)
    if m:
        metrics['comment_count'] = int(m.group(1))

    # 購入可能フラグ・価格
    m = re.search(r'"priceTax"\s*:\s*(\d+)', html)
    if m:
        metrics['price_tax'] = int(m.group(1))

    # PV数（公開されている場合のみ）
    m = re.search(r'"viewCount"\s*:\s*(\d+)', html)
    if m:
        metrics['view_count'] = int(m.group(1))

    # タイトル（変更検知用）
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if m:
        metrics['og_title'] = m.group(1)[:120]

    # 公開状態
    m = re.search(r'"status"\s*:\s*"([^"]+)"', html)
    if m:
        metrics['status'] = m.group(1)

    return metrics


def append_log(timestamp: str, target: dict, metrics: dict):
    """CSV にログ追記"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not OUTPUT_CSV.exists()

    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if is_new:
            w.writerow([
                'timestamp', 'article_id', 'title',
                'like_count', 'comment_count', 'view_count',
                'price_tax', 'status', 'url',
            ])
        w.writerow([
            timestamp,
            target['id'],
            target['title'],
            metrics.get('like_count', ''),
            metrics.get('comment_count', ''),
            metrics.get('view_count', ''),
            metrics.get('price_tax', ''),
            metrics.get('status', ''),
            target['url'],
        ])


def main():
    now = datetime.now().isoformat(timespec='seconds')
    print(f"=== note Performance Tracker @ {now} ===\n")

    for target in TARGETS:
        print(f"📄 {target['title']} ({target['url']})")
        html = fetch_note_html(target['url'])
        if not html:
            continue
        metrics = extract_metrics(html)
        for k, v in metrics.items():
            print(f"  {k}: {v}")
        append_log(now, target, metrics)
        print()

    print(f"✓ ログ保存: {OUTPUT_CSV}")
    print(f"  → 累積 {sum(1 for _ in open(OUTPUT_CSV))} 行")


if __name__ == '__main__':
    main()
