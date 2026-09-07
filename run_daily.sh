#!/bin/zsh
# Mac 側の自動取得（GitHub Actions と併用するハイブリッド運用）
#   1. リモートの最新を取り込む（GitHub 側が先に更新していれば無駄な二重保存をしない）
#   2. 取得（正午前で未更新なら scrape.py が何もせず終了する）
#   3. ダッシュボード再生成。実データが変わったときだけコミットして push
set -e
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

git pull --rebase --autostash --quiet || log "pull 失敗（ネットワーク？）。ローカルのまま続行"

/usr/bin/python3 scrape.py
/usr/bin/python3 build_site.py

if git diff --quiet -- docs/index.html; then
  log "データに変化なし。コミットしません"
  exit 0
fi

git add data/yuruverse.sqlite docs/index.html
git -c user.name="yuruverse-bot" -c user.email="actions@users.noreply.github.com" \
  commit --quiet -m "data: $(date '+%Y-%m-%d') snapshot (mac)"

# push が競合したら一度だけ取り込み直して再試行
if ! git push --quiet; then
  git pull --rebase --quiet && git push --quiet
fi
log "push 完了"
