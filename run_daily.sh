#!/bin/zsh
# Mac 側の自動取得（GitHub Actions と併用するハイブリッド運用）
#
# 設計方針:
#   - data/yuruverse.sqlite と docs/index.html は「取得し直せば再生成できる」ものなので git に統合させない。
#     .gitattributes + merge.keepupstream ドライバで、rebase 時は常に上流側を採用 → その後に再取得して差分があれば改めてコミット
#   - 前回の失敗（rebase 途中・未 push のコミット）が残っていても、毎回そこから正常に復帰する
#   - ログは事実だけを書く（失敗したら「失敗」と書いて exit 1）
set -u
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 多重起動防止（launchd の複数枠と手動実行が重ならないように）
if ! mkdir data/.lock 2>/dev/null; then
  log "別の実行が進行中のため終了"
  exit 0
fi
trap 'rmdir data/.lock 2>/dev/null' EXIT

git config merge.keepupstream.driver true

# 前回の後始末: 途中で止まった rebase/merge があれば破棄し、データ2ファイルの未コミット変更は捨てる（再生成するので）
git rebase --abort >/dev/null 2>&1 || true
git merge --abort  >/dev/null 2>&1 || true
git checkout --quiet -- data/yuruverse.sqlite docs/index.html 2>/dev/null || true
git branch --show-current | grep -qx main || { log "エラー: main ブランチではありません（$(git branch --show-current)）"; exit 1; }

# 上流の最新を取り込む。コードの未コミット変更は autostash で退避・復元される。
# データ2ファイルは keepupstream ドライバにより上流が勝ち、それだけの自分のコミットは空になって自動的に落ちる
sync_upstream() {
  if git pull --rebase --autostash --quiet origin main; then
    return 0
  fi
  git rebase --abort >/dev/null 2>&1 || true
  log "エラー: 上流の取り込みに失敗（ネットワーク断、またはコードの衝突）"
  return 1
}

scrape_and_build() {
  /usr/bin/python3 scrape.py && /usr/bin/python3 build_site.py
}

commit_if_changed() {
  if git diff --quiet -- docs/index.html; then
    return 1
  fi
  git add data/yuruverse.sqlite docs/index.html
  git -c user.name="yuruverse-bot" -c user.email="actions@users.noreply.github.com" \
    commit --quiet -m "data: $(date '+%Y-%m-%d') snapshot (mac)"
}

sync_upstream || exit 1
scrape_and_build || { log "エラー: 取得/生成に失敗"; exit 1; }
commit_if_changed || log "データに変化なし"

# 未 push のコミット（今回分、または過去に push できなかった分）があれば push
if [ "$(git rev-list --count origin/main..HEAD)" -eq 0 ]; then
  log "push するものなし"
  exit 0
fi
if git push --quiet origin main; then
  log "push 完了"
  exit 0
fi

# 競合（GitHub 側が先に更新）→ 上流を取り込み直し、取り直して差分があれば再コミット、もう一度だけ push
log "push が拒否されたため取り込み直して再試行"
sync_upstream || exit 1
scrape_and_build || { log "エラー: 再取得に失敗"; exit 1; }
commit_if_changed || true
if [ "$(git rev-list --count origin/main..HEAD)" -eq 0 ]; then
  log "上流が既に最新だったため push 不要"
  exit 0
fi
if git push --quiet origin main; then
  log "push 完了（再試行）"
  exit 0
fi
log "エラー: 再試行でも push に失敗"
exit 1
