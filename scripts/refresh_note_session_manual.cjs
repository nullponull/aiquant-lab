#!/usr/bin/env node
/**
 * note.com セッション手動更新ヘルパー
 *
 * 使い方:
 *   node /home/sol/aiquant-lab/scripts/refresh_note_session_manual.cjs
 *
 * 動作:
 *   1. ブラウザ（headed mode = 画面表示あり）が起動
 *   2. note.com のログインページに移動
 *   3. ユーザーが手動でログイン（メール+パスワード または OAuth）
 *   4. ログイン完了後、cookie が /home/sol/.note-state.json に自動保存
 *   5. ブラウザを閉じれば完了
 *
 * 完了後の確認:
 *   python3 /home/sol/daily-note-post/refresh_note_auth.py --state /home/sol/.note-state.json
 *   → "✓ 認証OK" と出れば成功
 *
 * その後 MCP の save_draft が動作するようになる
 */

const { chromium } = require('playwright');
const os = require('os');
const path = require('path');

const STATE_PATH = path.join(os.homedir(), '.note-state.json');
const NOTE_LOGIN_URL = 'https://note.com/login';

(async () => {
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('note.com セッション手動更新ヘルパー');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('');
  console.log('1. これから Chromium ブラウザが起動します（画面に表示）');
  console.log('2. note.com のログインページに自動移動');
  console.log('3. ご自身のアカウントでログインしてください');
  console.log('4. ログイン完了後、適当な画面に遷移してください');
  console.log('5. このスクリプトに戻り、Enter キーを押すと cookie を保存して終了');
  console.log('');
  console.log(`保存先: ${STATE_PATH}`);
  console.log('');

  const browser = await chromium.launch({
    headless: false,  // 重要: ユーザーに見える形で起動
    executablePath: '/home/sol/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome',
    args: ['--start-maximized']
  });

  const context = await browser.newContext({
    storageState: STATE_PATH,  // 既存の cookie を読み込み（一部生きている可能性）
    viewport: null,
  });

  const page = await context.newPage();
  await page.goto(NOTE_LOGIN_URL);

  console.log('✓ ブラウザ起動完了。note.com ログインページを表示中...');
  console.log('');
  console.log('ログイン完了したら、このターミナルで Enter を押してください...');

  // ユーザーが Enter を押すまで待機
  await new Promise(resolve => {
    process.stdin.once('data', resolve);
  });

  // 現在のページの cookie を保存
  await context.storageState({ path: STATE_PATH });

  console.log('');
  console.log('✓ Cookie保存完了: ' + STATE_PATH);
  console.log('');
  console.log('次のステップ:');
  console.log('  python3 /home/sol/daily-note-post/refresh_note_auth.py --state ' + STATE_PATH);
  console.log('  → 「✓ 認証OK」と出れば成功');
  console.log('');
  console.log('  その後、Claude経由で mcp__note-post__save_draft を再実行すれば下書き保存できます');

  await browser.close();
  process.exit(0);
})();
