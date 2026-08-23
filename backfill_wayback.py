#!/usr/bin/env python3
"""Wayback Machine のスナップショットから過去のランキングを復元して SQLite に取り込む。

- 対象: web.archive.org に保存された yurugp.jp/vote/2026* のページ
- 実データ(scrape.py が記録した日)より前の日付のみ追加し、既存データは上書きしない
- アーカイブは虫食い(クロールされた日・ページのみ)なので部分復元になる
"""
import datetime
import gzip
import json
import sys
import time
import urllib.request
from collections import defaultdict

from scrape import UA, DB_PATH, parse_page, compute_ranks, save
import sqlite3

# ランキングはトップページ(/)にも表示されるので両方探す
CDX_QUERIES = [
    "https://web.archive.org/cdx/search/cdx?url=yurugp.jp%2Fvote%2F2026*"
    "&output=json&filter=statuscode:200&filter=mimetype:text/html&from=20260401&collapse=digest",
    "https://web.archive.org/cdx/search/cdx?url=yurugp.jp%2F"
    "&output=json&filter=statuscode:200&filter=mimetype:text/html&from=20260401&collapse=digest",
]
JST = datetime.timezone(datetime.timedelta(hours=9))


def fetch(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":  # Wayback は gzip のまま返すことがある
        data = gzip.decompress(data)
    return data


def jst_date(ts: str) -> str:
    dt = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(JST).date().isoformat()


def existing_dates() -> set:
    con = sqlite3.connect(DB_PATH)
    try:
        return {r[0] for r in con.execute("SELECT DISTINCT date FROM snapshots")}
    finally:
        con.close()


def main():
    entries = []
    ts_i = url_i = None
    for cdx in CDX_QUERIES:
        raw = fetch(cdx)
        if raw.lstrip()[:1] != b"[":
            print("CDX API が JSON を返しませんでした（アーカイブがオフラインの可能性）", file=sys.stderr)
            sys.exit(2)
        rows = json.loads(raw)
        if len(rows) <= 1:
            continue
        header = rows[0]
        ts_i, url_i = header.index("timestamp"), header.index("original")
        entries.extend(rows[1:])
        time.sleep(1)
    if not entries:
        print("スナップショットが見つかりませんでした", file=sys.stderr)
        sys.exit(0)

    have = existing_dates()
    earliest_real = min(have) if have else "9999-12-31"

    # (JST日付, URL) ごとに最新のスナップショットを採用
    latest = {}
    for e in entries:
        d = jst_date(e[ts_i])
        if d >= earliest_real:
            continue  # 実データ以降は触らない
        key = (d, e[url_i])
        if key not in latest or e[ts_i] > latest[key]:
            latest[key] = e[ts_i]

    if not latest:
        print("復元対象の日付がありません（すべて実データ以降）", file=sys.stderr)
        return

    # 日付ごとに rank_range 別へ格納（順位計算は先頭から連続した範囲のみ有効）
    RANGE_ORDER = ["1-50", "51-100", "101-150", "151-200", "201-250", "251-300", "301+"]

    def range_of(url: str) -> str:
        if "rank_range=" in url:
            v = url.split("rank_range=")[-1].split("&")[0]
            return v.replace("%2B", "+").replace("%2b", "+")
        return "1-50"  # パラメータなしの /vote/2026 は 1-50 表示

    by_date = defaultdict(lambda: defaultdict(dict))  # date -> range -> {char_id: char}
    fetched = 0
    for (d, url), ts in sorted(latest.items()):
        wb_url = f"https://web.archive.org/web/{ts}id_/{url}"
        try:
            html = fetch(wb_url).decode("utf-8", errors="replace")
        except Exception as ex:
            print(f"  取得失敗 {d} {url}: {ex}", file=sys.stderr)
            continue
        rr = range_of(url)
        n = 0
        for c in parse_page(html):
            by_date[d][rr][c["id"]] = c
            n += 1
        fetched += 1
        print(f"  {d} rank_range={rr:<8} {n} 件", file=sys.stderr)
        time.sleep(1.2)

    added = 0
    for d, ranges in sorted(by_date.items()):
        # 1-50 から連続して存在する範囲だけを使う（途中が欠けると順位がずれるため）
        chars = {}
        for rr in RANGE_ORDER:
            if rr not in ranges or not ranges[rr]:
                break
            chars.update(ranges[rr])
        char_list = list(chars.values())
        if len(char_list) < 10:
            print(f"  {d}: 先頭ページ欠落または {len(char_list)} 件のみ → スキップ", file=sys.stderr)
            continue
        compute_ranks(char_list)
        save(char_list, d)
        added += 1
        print(f"保存: {d} ({len(char_list)} キャラ)", file=sys.stderr)
    print(f"完了: {fetched} スナップショット取得, {added} 日分を追加", file=sys.stderr)


if __name__ == "__main__":
    main()
