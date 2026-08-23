#!/usr/bin/env python3
"""X の過去投稿などから過去ランキングを手動追加する。

使い方:
  python3 add_manual.py 2026-08-10 <<'EOF'
  いずにゃん 35000
  さかいさんだー 34000
  つなが竜ヌゥ 25000
  EOF

- 1行 = 「キャラ名 ポイント」(カンマ入り可)。順位は行の並びではなくポイントから計算
- キャラ名は characters テーブルと照合(部分一致可)。見つからなければエラー表示して中断
- 既にその日付の実データがある場合は上書きしない(--force で上書き)
"""
import argparse
import re
import sqlite3
import sys

from scrape import DB_PATH, compute_ranks, save


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("--force", action="store_true", help="既存の同日データがあっても追記・上書きする")
    args = ap.parse_args()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        sys.exit("日付は YYYY-MM-DD 形式で指定してください")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    existing = con.execute("SELECT COUNT(*) c FROM snapshots WHERE date=?", (args.date,)).fetchone()["c"]
    if existing and not args.force:
        sys.exit(f"{args.date} には既に {existing} 件のデータがあります。上書きするなら --force を付けてください")
    all_chars = {r["id"]: dict(r) for r in con.execute(
        "SELECT id, name, prefecture, organization, entry_no FROM characters")}
    con.close()

    entries = []
    errors = []
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(.+?)[\s　]+([\d,，]+)\s*(?:PT|pt|ポイント)?$", line)
        if not m:
            errors.append(f"解析できない行: {line}")
            continue
        name, pts = m.group(1).strip(), int(re.sub(r"[,，]", "", m.group(2)))
        hits = [c for c in all_chars.values() if c["name"] == name]
        if not hits:
            hits = [c for c in all_chars.values() if name in c["name"] or c["name"] in name]
        if len(hits) != 1:
            cand = ", ".join(c["name"] for c in hits[:5]) or "候補なし"
            errors.append(f"キャラ名を特定できません: 「{name}」 ({cand})")
            continue
        c = dict(hits[0])
        c["points"] = pts
        entries.append(c)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    if not entries:
        sys.exit("入力がありません")

    compute_ranks(entries)
    save(entries, args.date)
    print(f"保存: {args.date} に {len(entries)} 件")
    for c in entries:
        print(f"  {c['rank']}位 {c['name']} {c['points']:,} PT")
    print("build_site.py を実行するとダッシュボードに反映されます")


if __name__ == "__main__":
    main()
