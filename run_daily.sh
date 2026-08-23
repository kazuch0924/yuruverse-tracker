#!/bin/zsh
# 毎日の取得 + ダッシュボード再生成
set -e
cd "$(dirname "$0")"
/usr/bin/python3 scrape.py
/usr/bin/python3 build_site.py
echo "[$(date '+%Y-%m-%d %H:%M:%S')] done"
