"""SQLite DB for claim forward-testing"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("/home/sol/aiquant-lab/data/claims/claims.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL,
    source_item_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_author TEXT,
    raw_text TEXT NOT NULL,
    asset TEXT NOT NULL,            -- 'BTC', 'ETH', 'SPY', 'AAPL', etc.
    asset_class TEXT NOT NULL,      -- 'crypto', 'us_stock', 'jp_stock', 'fx'
    direction TEXT NOT NULL,        -- 'LONG', 'SHORT', 'NEUTRAL'
    horizon_hours REAL NOT NULL,    -- 24.0, 72.0, 168.0
    target_pct REAL,                -- expected return % (NULL if unknown)
    target_price REAL,              -- specific price target (NULL if unknown)
    conviction_score INTEGER,       -- 1-10 LLM-judged
    entry_snapshot_price REAL,      -- T=0 price
    entry_snapshot_at TEXT,
    entry_currency TEXT,            -- 'USD', 'JPY'
    expires_at TEXT NOT NULL,       -- when to verify
    extracted_meta TEXT,            -- JSON of extra fields
    UNIQUE(source_item_url, asset, direction, horizon_hours)
);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    verified_at TEXT NOT NULL,
    exit_price REAL NOT NULL,
    raw_return_pct REAL NOT NULL,           -- (exit - entry) / entry * 100
    directional_return_pct REAL NOT NULL,   -- raw_return * sign(direction)
    hypothetical_jpy_pl INTEGER NOT NULL,   -- ¥10000 invested, PL in yen
    outcome TEXT NOT NULL,                  -- 'WIN', 'LOSS', 'NEUTRAL'
    target_hit BOOLEAN,                     -- did it reach target?
    notes TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);

CREATE INDEX IF NOT EXISTS idx_claims_expires ON claims(expires_at);
CREATE INDEX IF NOT EXISTS idx_claims_asset ON claims(asset);
CREATE INDEX IF NOT EXISTS idx_verifs_claim ON verifications(claim_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_claim(claim: dict) -> Optional[int]:
    """主張を登録。重複（同 URL × 銘柄 × 方向 × 期間）は無視。

    Returns: 新規の claim_id、または既存なら None
    """
    init_db()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO claims (
                    detected_at, source_item_url, source_name, source_author,
                    raw_text, asset, asset_class, direction, horizon_hours,
                    target_pct, target_price, conviction_score,
                    entry_snapshot_price, entry_snapshot_at, entry_currency,
                    expires_at, extracted_meta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim["detected_at"],
                    claim["source_item_url"],
                    claim["source_name"],
                    claim.get("source_author"),
                    claim["raw_text"],
                    claim["asset"],
                    claim["asset_class"],
                    claim["direction"],
                    claim["horizon_hours"],
                    claim.get("target_pct"),
                    claim.get("target_price"),
                    claim.get("conviction_score"),
                    claim.get("entry_snapshot_price"),
                    claim.get("entry_snapshot_at"),
                    claim.get("entry_currency", "USD"),
                    claim["expires_at"],
                    json.dumps(claim.get("extracted_meta", {}), ensure_ascii=False),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_claim_snapshot(claim_id: int, price: float, currency: str) -> None:
    """T=0 スナップショットを記録"""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE claims SET
                entry_snapshot_price = ?,
                entry_snapshot_at = ?,
                entry_currency = ?
            WHERE id = ?
            """,
            (price, datetime.now(timezone.utc).isoformat(), currency, claim_id),
        )
        conn.commit()


def get_pending_verifications(now_iso: str | None = None) -> list[dict]:
    """expires_at <= now で未検証の claims を取得"""
    init_db()
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.* FROM claims c
            LEFT JOIN verifications v ON v.claim_id = c.id
            WHERE c.expires_at <= ?
              AND v.id IS NULL
              AND c.entry_snapshot_price IS NOT NULL
            ORDER BY c.expires_at ASC
            """,
            (now_iso,),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_verification(claim_id: int, verification: dict) -> int:
    """検証結果を登録"""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO verifications (
                claim_id, verified_at, exit_price,
                raw_return_pct, directional_return_pct,
                hypothetical_jpy_pl, outcome, target_hit, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                verification["verified_at"],
                verification["exit_price"],
                verification["raw_return_pct"],
                verification["directional_return_pct"],
                verification["hypothetical_jpy_pl"],
                verification["outcome"],
                verification.get("target_hit"),
                verification.get("notes", ""),
            ),
        )
        conn.commit()
        return cur.lastrowid


def stats_summary(days_back: int = 30) -> dict:
    """過去 N 日分の集計"""
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.source_name, c.asset_class, c.asset, c.direction,
                v.outcome, v.directional_return_pct, v.hypothetical_jpy_pl,
                v.verified_at
            FROM verifications v
            JOIN claims c ON c.id = v.claim_id
            WHERE v.verified_at >= datetime('now', ?)
            """,
            (f"-{days_back} days",),
        ).fetchall()

    total = len(rows)
    if total == 0:
        return {"total": 0, "win_rate": None, "avg_return_pct": None,
                "by_source": {}, "by_asset_class": {}}

    wins = sum(1 for r in rows if r["outcome"] == "WIN")
    avg_return = sum(r["directional_return_pct"] for r in rows) / total
    total_pl = sum(r["hypothetical_jpy_pl"] for r in rows)

    by_source: dict[str, list] = {}
    by_class: dict[str, list] = {}
    for r in rows:
        by_source.setdefault(r["source_name"], []).append(r)
        by_class.setdefault(r["asset_class"], []).append(r)

    def aggregate(rows_list):
        n = len(rows_list)
        if n == 0:
            return {}
        w = sum(1 for r in rows_list if r["outcome"] == "WIN")
        return {
            "n": n,
            "win_rate": w / n,
            "avg_return_pct": sum(r["directional_return_pct"] for r in rows_list) / n,
            "total_pl_jpy": sum(r["hypothetical_jpy_pl"] for r in rows_list),
        }

    return {
        "total": total,
        "win_rate": wins / total,
        "avg_return_pct": avg_return,
        "total_pl_jpy": total_pl,
        "by_source": {k: aggregate(v) for k, v in by_source.items()},
        "by_asset_class": {k: aggregate(v) for k, v in by_class.items()},
    }


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
