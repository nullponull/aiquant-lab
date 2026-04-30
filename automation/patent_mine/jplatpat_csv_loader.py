"""J-PlatPat CSV エクスポートを読み込む

J-PlatPat の検索結果には「CSV出力」ボタンがあり、人間操作で大量取得可能。
そこから取得した CSV を Claude スコアリング pipeline に流し込む。

CSV カラム例（J-PlatPat の標準形式）:
- 文献番号 (公開番号)
- 出願番号
- 出願日
- 公開日 / 公報発行日
- 発明の名称
- 出願人/権利者
- 発明者
- IPC
- FI
- ステータス (登録 / 消滅 / 期間満了 等)

期限切れフィルター: 公開日が 20 年以上前 OR ステータスが「消滅」「期間満了」
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jplatpat_csv")


def detect_columns(headers: list[str]) -> dict[str, str]:
    """ヘッダーから J-PlatPat 標準カラム名を推測"""
    mapping: dict[str, str] = {}
    for h in headers:
        h_clean = h.strip().replace("　", "")
        if "文献番号" in h_clean or "公開番号" in h_clean or "公報番号" in h_clean:
            mapping["patent_number"] = h
        elif "出願番号" in h_clean:
            mapping["application_number"] = h
        elif "出願日" in h_clean:
            mapping["application_date"] = h
        elif "公開日" in h_clean or "公報発行日" in h_clean:
            mapping["publication_date"] = h
        elif "発明の名称" in h_clean or "考案の名称" in h_clean or "名称" == h_clean:
            mapping["title"] = h
        elif "権利者" in h_clean or "出願人" in h_clean:
            mapping["assignee"] = h
        elif "発明者" in h_clean or "考案者" in h_clean:
            mapping["inventor"] = h
        elif h_clean == "IPC" or h_clean.startswith("IPC"):
            mapping["ipc"] = h
        elif h_clean == "FI" or h_clean.startswith("FI"):
            mapping["fi"] = h
        elif "ステータス" in h_clean or "経過状態" in h_clean or "権利状況" in h_clean:
            mapping["status"] = h
        elif "要約" in h_clean or "アブストラクト" in h_clean:
            mapping["abstract"] = h
    return mapping


def parse_jp_date(s: str) -> datetime | None:
    """日本式日付を datetime に。YYYY-MM-DD / YYYY/MM/DD / 平成XX年/令和XX年 対応"""
    s = s.strip().replace("　", "").replace(" ", "")
    if not s:
        return None
    # YYYY-MM-DD or YYYY/MM/DD
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # 和暦 - 平成は 1989 年= 平成 1 年, 令和は 2019 年= 令和 1 年
    import re
    m = re.match(r"平成(\d+)年(\d+)月(\d+)日", s)
    if m:
        y = 1988 + int(m.group(1))
        return datetime(y, int(m.group(2)), int(m.group(3)))
    m = re.match(r"令和(\d+)年(\d+)月(\d+)日", s)
    if m:
        y = 2018 + int(m.group(1))
        return datetime(y, int(m.group(2)), int(m.group(3)))
    return None


def is_expired(row: dict, columns: dict, expired_threshold_years: int = 20) -> bool:
    """この特許は期限切れか判定"""
    # ステータスベース
    status_col = columns.get("status")
    if status_col and status_col in row:
        status = row[status_col].strip()
        if any(kw in status for kw in ["消滅", "期間満了", "失効", "年金未納"]):
            return True

    # 公開日ベース (公開から 20 年経過 ≒ 出願から 19 年程度)
    pub_col = columns.get("publication_date") or columns.get("application_date")
    if pub_col and pub_col in row:
        pub_dt = parse_jp_date(row[pub_col])
        if pub_dt:
            cutoff = datetime.now() - timedelta(days=365 * expired_threshold_years)
            if pub_dt < cutoff:
                return True

    return False


def load_csv(csv_path: Path, expired_only: bool = True) -> list[dict]:
    """J-PlatPat の CSV を読み、Claude スコアリング用 dict にする"""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # J-PlatPat の CSV は Shift-JIS or UTF-8 BOM
    text = None
    for encoding in ["utf-8-sig", "utf-8", "cp932", "shift_jis"]:
        try:
            text = csv_path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        raise UnicodeDecodeError("不明なエンコーディング", b"", 0, 0, csv_path.name)

    reader = csv.DictReader(text.splitlines())
    headers = reader.fieldnames or []
    logger.info(f"検出ヘッダー: {headers}")

    columns = detect_columns(headers)
    logger.info(f"カラムマッピング: {columns}")

    if not columns.get("patent_number") or not columns.get("title"):
        logger.error("必須カラム (文献番号 or 名称) が見つかりません")
        return []

    patents: list[dict] = []
    skipped_alive = 0
    skipped_no_data = 0
    for row in reader:
        title = (row.get(columns["title"]) or "").strip()
        if not title:
            skipped_no_data += 1
            continue
        if expired_only and not is_expired(row, columns):
            skipped_alive += 1
            continue

        patent = {
            "patent_number": (row.get(columns["patent_number"]) or "").strip(),
            "title": title,
            "abstract": (row.get(columns.get("abstract", "")) or "").strip()[:1500],
            "claims": "",  # CSV にはないので別途 Detail Page 取得が必要
            "inventor": (row.get(columns.get("inventor", "")) or "").strip(),
            "assignee": (row.get(columns.get("assignee", "")) or "").strip(),
            "publication_date": (row.get(columns.get("publication_date", "")) or "").strip(),
            "ipc": (row.get(columns.get("ipc", "")) or "").strip(),
            "status": (row.get(columns.get("status", "")) or "").strip(),
        }
        patents.append(patent)

    logger.info(f"読み込み: {len(patents)} 件 (期限切れ判定済)")
    logger.info(f"スキップ - 権利存続中: {skipped_alive}, データ不足: {skipped_no_data}")
    return patents


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python jplatpat_csv_loader.py <csv_path>")
        sys.exit(1)
    patents = load_csv(Path(sys.argv[1]))
    print(f"\n=== 期限切れ {len(patents)} 件 ===")
    for p in patents[:5]:
        print(f"\n--- {p['patent_number']} ---")
        print(f"  Title: {p['title'][:80]}")
        print(f"  Pub: {p['publication_date']}")
        print(f"  Status: {p['status']}")
        print(f"  Assignee: {p['assignee'][:60]}")
