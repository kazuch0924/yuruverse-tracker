#!/usr/bin/env python3
"""ゆるバース (yurugp.jp) ランキングを取得して SQLite に日次スナップショットとして保存する。

使い方:
  python3 scrape.py            # 今日の日付で取得・保存
  python3 scrape.py --date 2026-08-20   # 日付を指定して保存(再実行時の上書きにも使う)
"""
import argparse
import datetime
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://yurugp.jp"
YEAR = 2026
RANK_RANGES = ["1-50", "51-100", "101-150", "151-200", "201-250", "251-300", "301%2B"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DB_PATH = Path(__file__).parent / "data" / "yuruverse.sqlite"

BLOCK_RE = re.compile(
    r'<span>([^<]+)</span>\s*<span>\|</span>\s*<span>([^<]*)</span>\s*</div>\s*'
    r'<h3[^>]*>\s*<a class="hover:text-blue-600" href="/characters/(\d+)">([^<]+)</a>\s*</h3>\s*'
    r'<div[^>]*>\s*エントリーNo\.(\d+)\s*</div>'
    r'.*?<div class="text-3xl font-bold text-\[#3493CE\]">([\d,]+)</div>',
    re.DOTALL,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_page(html: str):
    for m in BLOCK_RE.finditer(html):
        pref, org, cid, name, entry_no, points = m.groups()
        yield {
            "id": int(cid),
            "name": name.strip(),
            "prefecture": pref.strip(),
            "organization": org.strip(),
            "entry_no": int(entry_no),
            "points": int(points.replace(",", "")),
        }


JST = datetime.timezone(datetime.timedelta(hours=9))
# サイトの更新は正午頃。これより前に取得した値が「前回保存分と完全一致」なら未更新とみなして保存しない
GUARD_UNTIL = datetime.time(12, 30)


def now_jst() -> datetime.datetime:
    return datetime.datetime.now(JST)


def fetch_range(rr: str):
    html = fetch(f"{BASE}/vote/{YEAR}?rank_range={rr}")
    chars = list(parse_page(html))
    print(f"  {rr.replace('%2B', '+')}: {len(chars)} 件", file=sys.stderr)
    return chars


def looks_stale(first_page, today: str) -> bool:
    """1ページ目の全キャラが、今日より前の最新スナップショットと同じポイントなら「サイト未更新」と判断する。"""
    if not first_page or not DB_PATH.exists():
        return False
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute("SELECT MAX(date) FROM snapshots WHERE date < ?", (today,)).fetchone()
        if not row or not row[0]:
            return False
        prev_date = row[0]
        prev = dict(con.execute("SELECT character_id, points FROM snapshots WHERE date = ?", (prev_date,)).fetchall())
    finally:
        con.close()
    if len(prev) < len(first_page):
        return False  # 前回分が部分データ(手入力など)なら比較しない
    return all(prev.get(c["id"]) == c["points"] for c in first_page)


def scrape_all(today: str, guard: bool):
    chars = {}
    first = fetch_range(RANK_RANGES[0])
    if guard and now_jst().time() < GUARD_UNTIL and looks_stale(first, today):
        print(f"サイト未更新（{now_jst():%H:%M} JST・前回保存分と同一）のため保存しません", file=sys.stderr)
        return None
    for c in first:
        chars[c["id"]] = c
    for rr in RANK_RANGES[1:]:
        time.sleep(1.5)  # サイトに負荷をかけない
        for c in fetch_range(rr):
            chars[c["id"]] = c
    return list(chars.values())


def compute_ranks(chars):
    """同点は同順位（standard competition ranking）。サイト表示と同じ方式。"""
    chars.sort(key=lambda c: -c["points"])
    rank = 0
    prev_points = None
    for i, c in enumerate(chars, start=1):
        if c["points"] != prev_points:
            rank = i
            prev_points = c["points"]
        c["rank"] = rank
    return chars


def init_db(con):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            prefecture TEXT,
            organization TEXT,
            entry_no INTEGER
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            date TEXT NOT NULL,
            character_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            points INTEGER NOT NULL,
            PRIMARY KEY (date, character_id)
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_char ON snapshots(character_id, date);
        """
    )


def save(chars, date: str):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    init_db(con)
    with con:
        for c in chars:
            con.execute(
                "INSERT INTO characters(id, name, prefecture, organization, entry_no) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, prefecture=excluded.prefecture, "
                "organization=excluded.organization, entry_no=excluded.entry_no",
                (c["id"], c["name"], c["prefecture"], c["organization"], c["entry_no"]),
            )
            con.execute(
                "INSERT INTO snapshots(date, character_id, rank, points) VALUES(?,?,?,?) "
                "ON CONFLICT(date, character_id) DO UPDATE SET rank=excluded.rank, points=excluded.points",
                (date, c["id"], c["rank"], c["points"]),
            )
    con.close()


def main():
    ap = argparse.ArgumentParser()
    # 日付は必ず日本時間で決める（GitHub Actions の実行環境は UTC なので date.today() だと深夜にずれる）
    ap.add_argument("--date", default=now_jst().date().isoformat())
    ap.add_argument("--no-guard", action="store_true", help="正午前の未更新ガードを無効にして必ず保存する")
    args = ap.parse_args()

    print(f"取得開始: {args.date} ({now_jst():%H:%M} JST)", file=sys.stderr)
    chars = scrape_all(args.date, guard=not args.no_guard)
    if chars is None:
        sys.exit(0)  # 未更新スキップ。後段の build_site は差分なしになり、コミットも発生しない
    if len(chars) < 100:
        print(f"エラー: 取得件数が少なすぎます ({len(chars)} 件)。サイト構造が変わった可能性。", file=sys.stderr)
        sys.exit(1)
    compute_ranks(chars)
    save(chars, args.date)
    print(f"保存完了: {len(chars)} キャラクター ({args.date})", file=sys.stderr)


if __name__ == "__main__":
    main()
