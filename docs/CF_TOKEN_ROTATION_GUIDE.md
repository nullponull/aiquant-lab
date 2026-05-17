# Cloudflare API Token ローテーション手順書

> 作成日: 2026-05-17
> 対象: GitHub Secret `CLOUDFLARE_API_TOKEN` (nullponull/ai-blog-system)
> 必要時間: 5分

---

## 背景

このセッションで提供いただいたトークン `cfut_gid...` がチャット履歴に残ったため、セキュリティベストプラクティスとして **Revoke + 新規発行** を推奨します。

同時に、新トークンには **Zone Cache Purge 権限** を含めることで、今後のデプロイ時の自動cache purgeが効くようになります。

---

## ステップ1: 既存トークン Revoke

1. https://dash.cloudflare.com/profile/api-tokens にアクセス
2. 現在の `CLOUDFLARE_API_TOKEN` (今回提供したもの) を見つける
3. 右側「Roll」または「Delete」をクリック
4. 確認 → Revoke完了

---

## ステップ2: 新規トークン発行（推奨権限）

### Custom Token を作成

「Create Token」→「Create Custom Token」

### Token name
`ai-blog-system-deploy-2026`

### Permissions（4つ追加）

1. **Account** → Cloudflare Pages → **Edit**
2. **Account** → Account Settings → **Read**
3. **Zone** → Cache Purge → **Purge**
4. **Zone** → Zone → **Read**

### Account Resources
- Include → Specific account → `Pokesapo0@gmail.com's Account`

### Zone Resources
- Include → All zones from account (上の account 指定で OK)

### TTL（推奨）
- Start: 即時
- End: **365日後**（毎年ローテーション）

### IP Address Filtering（オプション）
- GitHub Actions の IP範囲を指定するとさらに堅牢
- ただし GitHub Actions の IP は変動するので、通常は不要

### Create Summary 確認 → Create Token

→ **トークン文字列が画面に1回だけ表示される。コピーしておく**。

---

## ステップ3: GitHub Secret 更新

### A. gh CLI で更新（推奨）

```bash
unset GITHUB_TOKEN
echo "新しいトークン文字列をペースト" | snap run gh secret set CLOUDFLARE_API_TOKEN \
  --repo nullponull/ai-blog-system
```

### B. GitHub Web UI で更新

1. https://github.com/nullponull/ai-blog-system/settings/secrets/actions にアクセス
2. `CLOUDFLARE_API_TOKEN` の「Update」をクリック
3. 新トークン貼り付け → Save

---

## ステップ4: 動作確認

### 手動 workflow_dispatch でテスト

```bash
unset GITHUB_TOKEN
snap run gh workflow run "Cloudflare Pages Deploy" \
  --repo nullponull/ai-blog-system --ref main
```

GitHub Actions のログで `Purge Cloudflare edge cache` ステップが「✓ Cloudflare cache purged successfully」を出すか確認。

```bash
# 直近run確認
snap run gh run list --repo nullponull/ai-blog-system \
  --workflow="Cloudflare Pages Deploy" --limit 1

# ログ確認
snap run gh run view --log --repo nullponull/ai-blog-system \
  $(snap run gh run list --repo nullponull/ai-blog-system \
    --workflow="Cloudflare Pages Deploy" --limit 1 --json databaseId --jq '.[0].databaseId') \
  | grep -E "Zone ID|Purge response|cache purged"
```

---

## ステップ5: 旧トークン使用箇所の洗い出し

念のため、他のリポジトリ・スクリプトで旧トークンを使っていないか確認:

```bash
# ローカルのconfigやenvファイルに混入していないか
grep -r "cfut_gid" /home/sol/ 2>/dev/null | grep -v "node_modules\|__pycache__"

# 出てきたファイルは新トークンに更新するか、env から読むよう修正
```

---

## チェックリスト

- [ ] 旧トークン Revoke 完了
- [ ] 新トークン発行（4つの権限付与）
- [ ] GitHub Secret 更新
- [ ] workflow_dispatch でテスト → ログに「purged successfully」確認
- [ ] ローカル `grep -r "cfut_gid"` で漏洩確認
- [ ] このチャット履歴も適切な範囲で削除 or アーカイブ

---

## 今後の運用

- **年1回ローテーション**（TTL設定通り）
- **GitHub Actions 失敗時の通知**: 既存の Slack/メール通知に接続
- **権限の最小化**: 新規ワークフローを追加する時は、必要最小限の権限のみ追加
