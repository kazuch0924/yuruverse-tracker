# ゆるバースウォッチ

[ゆるバース](https://yurugp.jp/vote)（ゆるキャラグランプリ実行委員会）の公表ランキングを毎日記録し、
順位変動・日次獲得ポイントを見られる非公式トラッカー。

## 構成

| ファイル | 役割 |
|---|---|
| `scrape.py` | yurugp.jp のランキング7ページを取得し `data/yuruverse.sqlite` に日次スナップショット保存 |
| `build_site.py` | SQLite から自己完結型ダッシュボード `docs/index.html` を生成 |
| `template.html` | ダッシュボードの雛形（データは `/*__DATA__*/` に埋め込み） |
| `run_daily.sh` | 取得 + 生成をまとめて実行 |
| `launchd/…plist` | Mac ローカルで毎日 12:05 に自動実行するための LaunchAgent |
| `.github/workflows/scrape.yml` | GitHub Actions で毎日 12:05 JST に自動実行（推奨） |

## データベース

```
characters(id, name, prefecture, organization, entry_no)
snapshots(date, character_id, rank, points)   -- 1日1行/キャラ
```

同点は同順位（サイト表示と同じ standard competition ranking）。

## 手動実行

```bash
./run_daily.sh
```

同日に再実行するとその日のスナップショットが上書きされる（重複しない）。

## 運用（2026-09-07 からハイブリッド）

- **公開ページ**: https://kazuch0924.github.io/yuruverse-tracker/ （GitHub Pages、`main` の `/docs` を配信）
- **Mac 側（launchd）**: 12:03 / 12:18 / 12:33 / 12:48 / 13:30 に `run_daily.sh` を実行。Mac が起きていればこれで正午すぎに即反映される
- **GitHub Actions**: 12:07〜19:22 に8回予約（フォールバック）。GitHub の無料スケジューラは慢性的に4〜5時間遅れるため、実際の実行は夕方になる。Mac が閉じていた日はこちらが拾う
- 両者が衝突しない仕組み:
  - `scrape.py` は正午前（12:30 JST 前）に取得した値が前回保存分と完全一致なら「未更新」として保存しない
  - 取得日付は常に日本時間で決める（Actions の実行環境は UTC のため）
  - コミットは `docs/index.html` に差分があるときだけ。同じデータを二度保存しても何も起きない
  - `run_daily.sh` は先に `git pull --rebase` し、push が競合したら取り込み直して再試行
- 手動で今すぐ収集したいときは `./run_daily.sh`、または Actions の `daily-scrape` を Run workflow

### launchd の登録・解除

```bash
cp launchd/com.kazu.yuruverse-tracker.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kazu.yuruverse-tracker.plist
```

解除は `launchctl bootout gui/$(id -u)/com.kazu.yuruverse-tracker`。Mac がスリープ中に時刻を過ぎた場合は復帰時に実行される。

解除は `launchctl bootout gui/$(id -u)/com.kazu.yuruverse-tracker`。両方動かすと push が競合するのでどちらか一方にすること。

## 注意

- ゆるナビ投票は平日正午頃に前日分まで反映、ふるさと応援投票は毎週月曜に反映
- リクエストは1日7回 + 1.5秒間隔のウェイト付き（サイトに負荷をかけない）
- 取得件数が100件未満の場合はサイト構造変更とみなして保存せず異常終了する
