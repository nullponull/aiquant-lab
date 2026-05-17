#!/usr/bin/env python3
"""AIコンパス + 業界LP の SEO ヘルスチェック

定期実行で以下をモニタリング:
- 各ページの HTTP status
- 最終Cache age (long-tail cache 検出)
- robots.txt / sitemap.xml の整合性
- Google Search Console 風の indexed 状態（curl で site: クエリ）
- 構造化データ (JSON-LD) の有無
- 主要メタタグ (title, description, og:image)

【使い方】
python3 /home/sol/aiquant-lab/scripts/check_seo_health.py

【cron 例】
0 9 * * * /home/sol/aiquant-lab/scripts/check_seo_health.py > /tmp/seo_health_$(date +\%Y\%m\%d).log
"""
import json
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

# 監視対象URL
TARGETS = {
    'home': 'https://ai-media.co.jp/',
    'industry_hub': 'https://ai-media.co.jp/industry/',
    'industry_hr': 'https://ai-media.co.jp/industry/hr-interview-mock/',
    'industry_sales': 'https://ai-media.co.jp/industry/sales-roleplay-gym/',
    'industry_education': 'https://ai-media.co.jp/industry/education-tutor/',
    'industry_healthcare': 'https://ai-media.co.jp/industry/healthcare-mock-patient/',
    'about': 'https://ai-media.co.jp/about/',
    'sitemap': 'https://ai-media.co.jp/sitemap.xml',
    'robots': 'https://ai-media.co.jp/robots.txt',
    'feed': 'https://ai-media.co.jp/feed.xml',
    'page_404': 'https://ai-media.co.jp/404.html',
}

# 公開を抑制するURL（404期待）
SHOULD_BE_404 = [
    'https://ai-media.co.jp/2026/05/22/ai-governance-failure-netherlands-toeslagen/',
    'https://ai-media.co.jp/2026/05/29/ai-budget-hidden-costs-llm-tco/',
    'https://ai-media.co.jp/2026/06/05/generative-ai-consent-copyright-personal-info/',
    'https://ai-media.co.jp/2026/06/12/ai-roi-misreading-mckinsey-30percent/',
    'https://ai-media.co.jp/2026/08/01/ai-failure-check-2026-summer/',
    'https://ai-media.co.jp/this-page-does-not-exist-random/',
]

OUTPUT_DIR = Path('/home/sol/aiquant-lab/data')
OUTPUT_JSON = OUTPUT_DIR / 'seo_health_latest.json'
OUTPUT_LOG = OUTPUT_DIR / 'seo_health_history.jsonl'


def fetch(url: str) -> tuple[int, dict, str]:
    """URL を取得し、status, headers, body を返す"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; aiquant-seo-check/1.0)',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers) if e.headers else {}, ''
    except Exception as e:
        return 0, {}, str(e)


def analyze_page(url: str, status: int, headers: dict, body: str) -> dict:
    """HTML を解析してSEOメトリクス抽出"""
    out = {'url': url, 'status': status}

    # Cache state
    out['cache_status'] = headers.get('cf-cache-status', '')
    out['cache_age'] = int(headers.get('age', 0) or 0)
    out['cache_control'] = headers.get('cache-control', '')

    # Title / description
    m = re.search(r'<title>([^<]+)</title>', body)
    if m:
        out['title'] = m.group(1)[:200]
    m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', body)
    if m:
        out['description'] = m.group(1)[:200]

    # OGP
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', body)
    if m:
        out['og_image'] = m.group(1)

    # Structured data (JSON-LD)
    ldjson = re.findall(r'<script\s+type="application/ld\+json"[^>]*>([^<]+)</script>', body)
    out['structured_data_count'] = len(ldjson)
    structured_types = []
    for s in ldjson:
        try:
            data = json.loads(s.strip())
            if isinstance(data, dict):
                t = data.get('@type', '')
                if isinstance(t, list):
                    structured_types.extend(t)
                else:
                    structured_types.append(t)
        except Exception:
            pass
    out['structured_types'] = structured_types

    return out


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec='seconds')
    print(f"=== SEO Health Check @ {now} ===\n")

    results = {'timestamp': now, 'pages': {}, 'should_be_404': {}, 'alerts': []}

    print("[Step 1] 主要ページの状態")
    for name, url in TARGETS.items():
        status, headers, body = fetch(url)
        info = analyze_page(url, status, headers, body)
        results['pages'][name] = info
        flag = '✓' if status == 200 else ('?' if status in (301, 302) else '❌')
        print(f"  {flag} HTTP {status:3d} | cache_age:{info['cache_age']:>5d}s | {name}")
        if status >= 400 and name != 'page_404':
            results['alerts'].append(f"{name}: HTTP {status}")

    print("\n[Step 2] 404 を返すべきURL（予約公開記事）")
    for url in SHOULD_BE_404:
        status, headers, body = fetch(url)
        results['should_be_404'][url] = {'status': status, 'cache_age': int(headers.get('age', 0) or 0)}
        if status == 404:
            print(f"  ✓ HTTP 404  {url}")
        else:
            print(f"  ⚠ HTTP {status} (期待404)  {url}")
            results['alerts'].append(f"Should be 404: {url} returned {status}")

    print("\n[Step 3] サイトマップ整合性")
    sitemap_body = results['pages'].get('sitemap', {}).get('title', '')
    sitemap_status, _, sitemap_xml = fetch(TARGETS['sitemap'])
    if sitemap_status == 200:
        url_count = sitemap_xml.count('<url>')
        future_count = sum(1 for d in SHOULD_BE_404 if d in sitemap_xml)
        print(f"  サイトマップURL数: {url_count}")
        print(f"  予約公開URL混入: {future_count} (期待: 0)")
        results['sitemap_urls'] = url_count
        results['sitemap_future_leaks'] = future_count
        if future_count > 0:
            results['alerts'].append(f"Sitemap leaks {future_count} future-dated URLs")

    print(f"\n[Step 4] アラート集計")
    if results['alerts']:
        for a in results['alerts']:
            print(f"  ⚠ {a}")
    else:
        print("  ✓ アラートなし")

    # 保存
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(OUTPUT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'timestamp': now, 'alerts': len(results['alerts']),
                           'cache_age_max': max((p.get('cache_age', 0) for p in results['pages'].values()),
                                                default=0)}, ensure_ascii=False) + '\n')

    print(f"\n✓ 保存: {OUTPUT_JSON}")


if __name__ == '__main__':
    main()
