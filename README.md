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

## 運用（2026-08-23 から）

- **毎日の収集は GitHub Actions**（12:05 JST）が行い、`main` にコミットする
- **公開ページ**: https://kazuch0924.github.io/yuruverse-tracker/ （GitHub Pages、`main` の `/docs` を配信）
- ローカルの launchd は二重取得を避けるため停止済み。ローカルで最新データが欲しいときは `git pull`
- 手動で今すぐ収集したいときは Actions の `daily-scrape` を Run workflow、またはローカルで `./run_daily.sh` して push

### ローカル自動実行に戻す場合（launchd）

```bash
cp launchd/com.kazu.yuruverse-tracker.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kazu.yuruverse-tracker.plist
```

解除は `launchctl bootout gui/$(id -u)/com.kazu.yuruverse-tracker`。両方動かすと push が競合するのでどちらか一方にすること。

## 注意

- ゆるナビ投票は平日正午頃に前日分まで反映、ふるさと応援投票は毎週月曜に反映
- リクエストは1日7回 + 1.5秒間隔のウェイト付き（サイトに負荷をかけない）
- 取得件数が100件未満の場合はサイト構造変更とみなして保存せず異常終了する
