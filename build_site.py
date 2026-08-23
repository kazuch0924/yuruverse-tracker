#!/usr/bin/env python3
"""SQLite の日次スナップショットから自己完結型ダッシュボード docs/index.html を生成する。"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "yuruverse.sqlite"
TEMPLATE = ROOT / "template.html"
OUT = ROOT / "docs" / "index.html"


def build_payload():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    dates = [r["date"] for r in con.execute("SELECT DISTINCT date FROM snapshots ORDER BY date")]
    date_idx = {d: i for i, d in enumerate(dates)}

    chars = {}
    for r in con.execute("SELECT id, name, prefecture, organization, entry_no FROM characters"):
        chars[r["id"]] = {
            "id": r["id"],
            "n": r["name"],
            "p": r["prefecture"],
            "o": r["organization"],
            "e": r["entry_no"],
            "pts": [None] * len(dates),
            "rks": [None] * len(dates),
        }

    for r in con.execute("SELECT date, character_id, rank, points FROM snapshots"):
        c = chars.get(r["character_id"])
        if c is None:
            continue
        i = date_idx[r["date"]]
        c["pts"][i] = r["points"]
        c["rks"][i] = r["rank"]

    con.close()

    # 最新スナップショットに存在するキャラのみ(過去に消えたキャラも履歴用に残すなら外す)
    latest = len(dates) - 1
    char_list = [c for c in chars.values() if c["pts"][latest] is not None]
    char_list.sort(key=lambda c: c["rks"][latest])
    return {"dates": dates, "chars": char_list}


def main():
    payload = build_payload()
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/", data_json)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"生成完了: {OUT} ({len(payload['chars'])} キャラ / {len(payload['dates'])} 日分, {len(html)//1024} KB)")


if __name__ == "__main__":
    main()
