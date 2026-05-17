#!/usr/bin/env python3
"""Gmail フィルタを自動設定 — info@ai-media.co.jp 問い合わせの仕分け

業界LP公開後の問い合わせを業界別ラベルに自動振り分け。
Gmail API を使うため、事前に OAuth セットアップが必要。

【事前準備】
1. Google Cloud Console で OAuth Client ID 作成 (Desktop app type)
2. credentials.json を /home/sol/.gmail-credentials.json に保存
3. 初回実行時にブラウザでGoogle認証 → トークン保存

【実行】
python3 /home/sol/aiquant-lab/scripts/setup_gmail_filters.py

【設定されるフィルタ】
- AI面接練習Mock → Inquiry/HR
- 営業ロープレGym → Inquiry/Sales
- ライブAI家庭教師 → Inquiry/Education
- 医療問診シミュレータ → Inquiry/Healthcare
- AIコンパス（上記以外）→ Inquiry/Other
- 取材/ライター → Press
"""
import os
import sys
import json
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("⚠ Google API ライブラリが未インストール。以下を実行してください:")
    print("  pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.labels',
    'https://www.googleapis.com/auth/gmail.settings.basic',
]
CREDS_PATH = Path.home() / '.gmail-credentials.json'
TOKEN_PATH = Path.home() / '.gmail-token.json'

# ===== フィルタ定義 =====
LABELS = [
    'Inquiry/HR', 'Inquiry/Sales', 'Inquiry/Education',
    'Inquiry/Healthcare', 'Inquiry/Other', 'Press',
]

FILTERS = [
    {
        'criteria': {'subject': 'AI面接練習Mock OR HR OR 採用'},
        'action': {'addLabelIds': ['Inquiry/HR'], 'removeLabelIds': ['INBOX']},
        'note': 'HR問い合わせ → 重要マーク + Inquiry/HR',
    },
    {
        'criteria': {'subject': '営業ロープレGym OR Sales OR 商談'},
        'action': {'addLabelIds': ['Inquiry/Sales'], 'removeLabelIds': ['INBOX']},
        'note': 'Sales問い合わせ → Inquiry/Sales',
    },
    {
        'criteria': {'subject': 'AI家庭教師 OR Education OR 塾 OR 教師'},
        'action': {'addLabelIds': ['Inquiry/Education'], 'removeLabelIds': ['INBOX']},
        'note': 'Education問い合わせ → Inquiry/Education',
    },
    {
        'criteria': {'subject': '医療問診 OR 病院 OR 医学部 OR 研修医'},
        'action': {
            'addLabelIds': ['Inquiry/Healthcare', 'IMPORTANT'],
            'removeLabelIds': ['INBOX'],
        },
        'note': 'Healthcare問い合わせ → 重要マーク（高単価）',
    },
    {
        'criteria': {
            'subject': 'AIコンパス',
            'excludeChats': True,
        },
        'action': {'addLabelIds': ['Inquiry/Other']},
        'note': 'AIコンパス言及（業界外）→ Inquiry/Other',
    },
    {
        'criteria': {'subject': '取材 OR ライター OR PR OR プレス'},
        'action': {'addLabelIds': ['Press', 'IMPORTANT'], 'removeLabelIds': ['INBOX']},
        'note': '取材依頼 → 最優先',
    },
]


def get_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                print(f"⚠ {CREDS_PATH} が存在しません。")
                print("  Google Cloud Console で OAuth Client ID を発行し、保存してください。")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)


def ensure_labels(service):
    existing = service.users().labels().list(userId='me').execute().get('labels', [])
    existing_names = {l['name']: l['id'] for l in existing}
    label_ids = {}
    for name in LABELS:
        if name in existing_names:
            label_ids[name] = existing_names[name]
            print(f"  ✓ ラベル既存: {name}")
        else:
            body = {'name': name, 'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'}
            r = service.users().labels().create(userId='me', body=body).execute()
            label_ids[name] = r['id']
            print(f"  + ラベル作成: {name}")
    # 標準ラベル（IMPORTANT）のIDも含める
    label_ids['IMPORTANT'] = 'IMPORTANT'
    label_ids['INBOX'] = 'INBOX'
    return label_ids


def create_filters(service, label_ids):
    existing = service.users().settings().filters().list(userId='me').execute().get('filter', [])
    existing_criteria = set()
    for f in existing:
        crit = f.get('criteria', {})
        existing_criteria.add(json.dumps(crit, sort_keys=True))

    for f_def in FILTERS:
        crit_key = json.dumps(f_def['criteria'], sort_keys=True)
        if crit_key in existing_criteria:
            print(f"  ✓ フィルタ既存: {f_def['note']}")
            continue

        # action の label name を ID に解決
        action = dict(f_def['action'])
        for key in ['addLabelIds', 'removeLabelIds']:
            if key in action:
                action[key] = [label_ids.get(n, n) for n in action[key]]

        body = {'criteria': f_def['criteria'], 'action': action}
        service.users().settings().filters().create(userId='me', body=body).execute()
        print(f"  + フィルタ作成: {f_def['note']}")


def main():
    print("=== Gmail フィルタ自動設定 (info@ai-media.co.jp) ===\n")
    service = get_service()
    print("\n[Step 1] ラベル作成/確認:")
    label_ids = ensure_labels(service)
    print("\n[Step 2] フィルタ作成:")
    create_filters(service, label_ids)
    print("\n✓ 完了。Gmail Web で確認してください。")
    print("  → https://mail.google.com/mail/u/0/#settings/filters")


if __name__ == '__main__':
    main()
