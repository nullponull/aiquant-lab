# WORLDmonitor 自己ホストセットアップガイド

連載「AIで投資の壁を越える」第 5 回以降で使用する WORLDmonitor の構築手順。

---

## WORLDmonitor とは

GitHub: https://github.com/koala73/worldmonitor

リアルタイム世界情勢監視ダッシュボード。本連載では以下の用途で使用：
- 500+ 国際ニュースフィードからのイベント収集
- 92 取引所の価格データ統合
- クロスストリーム相関分析
- 国家インテリジェンスインデックス
- ローカル LLM (Ollama) によるイベント解釈

ライセンス: AGPL-3.0（個人・研究・教育利用可、商用利用は別途ライセンス必要）

---

## 動作要件

### 最小構成（本連載で必要な範囲）

```
CPU:    4 コア以上
RAM:    8GB 以上（Ollama 含むなら 16GB 推奨）
Disk:   20GB 以上（データキャッシュ + Ollama モデル）
OS:     Linux (Ubuntu 22.04+ 推奨), macOS, Windows + WSL2
```

### 推奨構成

```
CPU:    8 コア以上
RAM:    32GB（Ollama で大きめモデル使用時）
GPU:    NVIDIA RTX 3060 以上（Ollama 高速化）
Disk:   100GB 以上（長期データ保管）
```

---

## セットアップ手順（Ubuntu 22.04 / WSL2）

### Step 1: 必要なツールのインストール

```bash
# Node.js (20.x 以上)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Rust (Tauri 用)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# その他依存
sudo apt install -y build-essential libwebkit2gtk-4.0-dev \
  libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev

# Docker (Ollama 用)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

### Step 2: WORLDmonitor のクローン

```bash
cd ~
git clone https://github.com/koala73/worldmonitor.git
cd worldmonitor
```

### Step 3: 依存インストール

```bash
npm install
```

### Step 4: 環境変数設定

```bash
cp .env.example .env  # サンプルがあればコピー
# 必要に応じて編集
```

主要な環境変数:
- `ANTHROPIC_API_KEY`: Claude 経由でのイベント解釈に使う場合
- `OPENAI_API_KEY`: GPT 経由の場合
- `OLLAMA_HOST`: ローカル Ollama を使う場合（推奨）

### Step 5: Ollama セットアップ（推奨）

LLM コストをゼロにするため、ローカル Ollama を使う：

```bash
# Ollama インストール
curl -fsSL https://ollama.com/install.sh | sh

# 軽量モデルをプル（推奨: Llama 3.2 3B）
ollama pull llama3.2:3b

# 起動確認
ollama run llama3.2:3b "Hello"
```

### Step 6: 開発サーバー起動

```bash
cd ~/worldmonitor
npm run dev
```

ブラウザで http://localhost:5173 にアクセスして動作確認。

---

## 投資シミュレーターとの統合

### Step 7: WORLDmonitor の API を呼び出す

WORLDmonitor は内部 API を持っている。aiquant-lab から呼び出すために、Python クライアントを実装：

```python
# code/worldmonitor_client.py
import requests
from datetime import datetime

class WorldMonitorClient:
    def __init__(self, base_url: str = "http://localhost:5173/api"):
        self.base_url = base_url

    def fetch_events(self, since: datetime, categories: list[str] = None) -> list[dict]:
        """指定日時以降のイベントを取得"""
        params = {"since": since.isoformat()}
        if categories:
            params["categories"] = ",".join(categories)
        r = requests.get(f"{self.base_url}/events", params=params)
        r.raise_for_status()
        return r.json()["events"]

    def fetch_finance_radar(self, exchange: str = None) -> dict:
        """ファイナンスレーダーから価格データ取得"""
        params = {"exchange": exchange} if exchange else {}
        r = requests.get(f"{self.base_url}/finance-radar", params=params)
        r.raise_for_status()
        return r.json()

    def get_intelligence_index(self) -> dict:
        """国家インテリジェンスインデックス取得"""
        r = requests.get(f"{self.base_url}/intelligence-index")
        r.raise_for_status()
        return r.json()
```

### Step 8: イベント駆動シミュレーターへの組み込み

```python
# code/experiments/run_episode5.py
from worldmonitor_client import WorldMonitorClient
from datetime import datetime, timedelta

wm = WorldMonitorClient()

# 過去 24 時間の重要イベントを取得
events = wm.fetch_events(
    since=datetime.now() - timedelta(hours=24),
    categories=["geopolitics", "finance", "macro"]
)

for event in events:
    print(f"[{event['timestamp']}] {event['headline']}")
    print(f"  Importance: {event['importance']}")
    print(f"  Sectors: {event['affected_sectors']}")
```

---

## トラブルシューティング

### `npm install` でエラー

Node.js のバージョン確認：
```bash
node --version  # 20.x 以上であること
```

### Tauri ビルドエラー

```bash
# Linux で webkit2gtk が見つからない場合
sudo apt install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev
```

### Ollama が遅い

GPU が使われているか確認：
```bash
nvidia-smi  # GPU 使用率を確認
```

CPU のみの場合は軽量モデル（3B 以下）を使う。

### メモリ不足

```bash
# Ollama モデルを軽量化
ollama pull llama3.2:1b  # 1B パラメータ版
```

---

## 運用 Tips

### 24 時間稼働させる場合

systemd サービスとして登録：

```bash
sudo tee /etc/systemd/system/worldmonitor.service > /dev/null <<EOF
[Unit]
Description=WORLDmonitor
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/worldmonitor
ExecStart=/usr/bin/npm run start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable worldmonitor
sudo systemctl start worldmonitor
```

### データ永続化

WORLDmonitor のデータは `data/` ディレクトリに保存される。バックアップ推奨：

```bash
# 日次バックアップ
0 3 * * * tar -czf ~/backup/worldmonitor-$(date +\%Y\%m\%d).tar.gz ~/worldmonitor/data/
```

---

## 連載第 5 回での使い方

第 5 回「コロナ暴落を AI は検知できたか」では：

1. WORLDmonitor を 2020 年 1 月時点のニュースアーカイブで再生
2. ニュース見出しから「パンデミック」関連シグナルを抽出
3. 通常時のベースライン vs パンデミック前期間の比較
4. 「AI が事前検知できたか」を定量化

実装イメージ:

```python
# 過去のニュースアーカイブを WORLDmonitor で再生
events_jan_2020 = wm.fetch_events_archive(
    start="2020-01-01",
    end="2020-03-15"
)

# パンデミック関連シグナルを LLM で抽出
pandemic_signals = []
for event in events_jan_2020:
    if "covid" in event["text"].lower() or "pandemic" in event["text"].lower():
        pandemic_signals.append({
            "timestamp": event["timestamp"],
            "severity": llm_score_severity(event["text"]),
        })

# 累積シグナルが閾値を超えた日を検出
detection_date = find_threshold_crossing(pandemic_signals, threshold=0.7)

# 実際の株価暴落開始日との時間差を計算
crash_start = "2020-02-20"
lead_time = calc_lead_time(detection_date, crash_start)
print(f"AI 事前検知のリードタイム: {lead_time} 日")
```

---

## ライセンスの注意

WORLDmonitor は AGPL-3.0 のため、本連載での使用は問題ありませんが：

- ✅ 教育・研究目的の自己ホスト OK
- ✅ note 記事での結果共有 OK
- ✅ GitHub での派生実装公開 OK（AGPL 継承）
- ❌ 有料 SaaS 化する場合は商用ライセンス必要

将来的に SaaS 化する場合は、作者 (Elie Habib 氏) との商用ライセンス契約を検討する。

---

## 次のステップ

1. ローカル環境でセットアップ完了
2. 主要な API エンドポイントの動作確認
3. 過去データのアーカイブ機能をテスト
4. aiquant-lab との統合テスト
5. 第 5 回記事の実験で本格使用

セットアップで詰まったら、WORLDmonitor の Issues セクションを参照：
https://github.com/koala73/worldmonitor/issues
