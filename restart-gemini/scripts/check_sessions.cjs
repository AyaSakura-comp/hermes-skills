#!/usr/bin/env node
/**
 * check_sessions.cjs — verify every chat session LazyGravity has bound in
 * antigravity.db still actually exists inside Antigravity.
 *
 * Why this exists (2026-07-21): a restart can leave the whole stack green —
 * units active, CDP answering, every renderer alive — while a bound
 * conversation has vanished from Antigravity's history. The bot then fails
 * with:
 *
 *   Failed to activate session "X" after N attempt(s)
 *   (direct: Chat title not found in side panel;
 *    past: Conversation not found in Past Conversations)
 *
 * That is NOT a restart problem and restarting again will never fix it — the
 * channel needs `/new` to bind a fresh session. This script tells the two
 * cases apart so the skill stops recommending a pointless restart.
 *
 * It drives the real UI, the same way the bot does: open the Past
 * Conversations widget (`.jetski-fast-pick`) in the workspace window, type the
 * title into the "Select a conversation" input, and see whether a row matches.
 *
 * Usage: node check_sessions.cjs
 * Exit code: 0 = every bound session resolvable, 1 = at least one is stale.
 */
const http = require('http');
const path = require('path');
const os = require('os');
const WebSocket = require('/home/chihmin/src/LazyGravity/node_modules/ws');
const Database = require('/home/chihmin/src/LazyGravity/node_modules/better-sqlite3');

const PORT = process.env.CDP_PORT || '9223';
const LG_DIR = '/home/chihmin/src/LazyGravity';
// LG_DB overridable so the detection can be exercised against a scratch copy
const DB_PATH = process.env.LG_DB || path.join(LG_DIR, 'antigravity.db');
// mirrors WORKSPACE_BASE_DIR in LazyGravity's .env
const WORKSPACE_BASE = process.env.WORKSPACE_BASE_DIR
    ? process.env.WORKSPACE_BASE_DIR.replace(/^~/, os.homedir())
    : path.join(os.homedir(), 'src');

const httpGet = (p) =>
    new Promise((resolve, reject) => {
        http.get({ host: '127.0.0.1', port: PORT, path: p }, (res) => {
            let body = '';
            res.on('data', (c) => (body += c));
            res.on('end', () => {
                try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
            });
        }).on('error', reject);
    });

/** Minimal CDP session over a page's WebSocket. */
function connect(wsUrl) {
    return new Promise((resolve, reject) => {
        const sock = new WebSocket(wsUrl, { perMessageDeflate: false });
        let nextId = 0;
        const waiters = new Map();
        sock.on('message', (m) => {
            let d;
            try { d = JSON.parse(m); } catch { return; }
            const w = waiters.get(d.id);
            if (w) { waiters.delete(d.id); w(d); }
        });
        sock.on('error', reject);
        sock.on('open', () => resolve({
            send(method, params, timeoutMs = 15000) {
                return new Promise((res) => {
                    const id = ++nextId;
                    const t = setTimeout(() => { waiters.delete(id); res({ error: 'timeout' }); }, timeoutMs);
                    waiters.set(id, (d) => { clearTimeout(t); res(d); });
                    sock.send(JSON.stringify({ id, method, params }));
                });
            },
            async evaluate(expression, timeoutMs) {
                const d = await this.send('Runtime.evaluate',
                    { expression, returnByValue: true, awaitPromise: true }, timeoutMs);
                return d.result && d.result.result ? d.result.result.value : { error: 'no result' };
            },
            close() { try { sock.close(); } catch {} },
        }));
    });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * The bot tries the side panel BEFORE Past Conversations, so this must too —
 * a freshly created chat is the active session but is not yet listed in Past
 * Conversations, and checking only the latter reports it as a false STALE.
 * Title extraction mirrors GET_CHAT_TITLE_SCRIPT in LazyGravity's
 * src/services/chatSessionService.ts ("Agent" = the empty-chat placeholder).
 */
const CHECK_SIDE_PANEL = (title) => `(() => {
    const wanted = ${JSON.stringify(title)}.toLowerCase().replace(/\\s+/g, ' ').trim();
    const panel = document.querySelector('.antigravity-agent-side-panel');
    if (!panel) return { found: false, current: '', reason: 'no panel' };
    const header = panel.querySelector('div[class*="border-b"]');
    const titleEl = header && header.querySelector('div[class*="text-ellipsis"]');
    let current = titleEl ? (titleEl.textContent || '').trim() : '';
    if (!current || current === 'Agent') {
        const activeRow = [...panel.querySelectorAll('div[class*="focusBackground"]')]
            .find((el) => el instanceof HTMLElement && el.offsetParent !== null);
        const activeTitle = activeRow && activeRow.querySelector('span.text-sm span, span.text-sm');
        const activeText = activeTitle ? (activeTitle.textContent || '').trim() : '';
        if (activeText) current = activeText;
    }
    const norm = (t) => (t || '').toLowerCase().replace(/\\s+/g, ' ').trim();
    if (norm(current) === wanted) return { found: true, current, how: 'active session' };
    // the bot also clicks any visible side-panel row whose text matches
    const row = [...panel.querySelectorAll('button, [role="button"], a, li, div, span')]
        .filter((el) => el instanceof HTMLElement && el.offsetParent !== null)
        .find((el) => norm(el.textContent) === wanted);
    if (row) return { found: true, current, how: 'side panel row' };
    return { found: false, current };
})()`;

const OPEN_PANEL = `(async () => {
    const isVis = (el) => el instanceof HTMLElement && el.offsetParent !== null;
    const findInput = () => [...document.querySelectorAll('input')]
        .find((e) => isVis(e) && /select a conversation/i.test(e.getAttribute('placeholder') || ''));
    if (findInput()) return 'already-open';
    const toggle = document.querySelector('[data-past-conversations-toggle]');
    if (!toggle) return 'no-toggle';
    (toggle.closest('button, [role="button"]') || toggle).click();
    await new Promise((r) => setTimeout(r, 1500));
    return findInput() ? 'opened' : 'failed-to-open';
})()`;

const FOCUS_INPUT = `(() => {
    const input = [...document.querySelectorAll('input')]
        .find((e) => e.offsetParent !== null && /select a conversation/i.test(e.getAttribute('placeholder') || ''));
    if (!input) return false;
    input.focus();
    return true;
})()`;

const READ_RESULTS = `(() => {
    const widget = document.querySelector('.jetski-fast-pick');
    if (!widget) return { error: 'panel closed' };
    const text = (widget.textContent || '').replace(/\\s+/g, ' ').trim();
    const input = widget.querySelector('input');
    return { query: input ? input.value : '', noItems: /no items found/i.test(text), text: text.slice(0, 400) };
})()`;

/** Type text as real key events — the widget's list is React-filtered on input. */
async function typeText(cdp, text) {
    for (const ch of text) {
        await cdp.send('Input.dispatchKeyEvent', { type: 'char', text: ch });
        await sleep(25);
    }
}

async function pressEscape(cdp) {
    const key = { key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 };
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', ...key });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', ...key });
}

(async () => {
    let rows;
    try {
        const db = new Database(DB_PATH, { readonly: true });
        rows = db.prepare(
            `SELECT channel_id, workspace_path, display_name
               FROM chat_sessions
              WHERE display_name IS NOT NULL AND TRIM(display_name) <> ''`,
        ).all();
        db.close();
    } catch (e) {
        console.log(`  cannot read ${DB_PATH}: ${e.message}`);
        process.exit(0);
    }

    if (!rows.length) { console.log('  no named chat sessions bound — nothing to verify'); return; }

    const pages = (await httpGet('/json/list'))
        .filter((p) => p.type === 'page' && /workbench/.test(p.url || ''));

    let stale = 0;
    for (const row of rows) {
        const abs = path.resolve(WORKSPACE_BASE, row.workspace_path || '.');
        const wsName = path.basename(abs);
        const title = row.display_name.trim();
        const page = pages.find((p) => (p.title || '').startsWith(`${wsName} - Antigravity`));

        if (!page) {
            console.log(`  ?  "${title}"  [${wsName}]  — no window open for this workspace (open it in Discord first)`);
            continue;
        }

        let cdp;
        try {
            cdp = await connect(page.webSocketDebuggerUrl);
        } catch (e) {
            console.log(`  ?  "${title}"  [${wsName}]  — CDP connect failed: ${e}`);
            continue;
        }

        try {
            const side = await cdp.evaluate(CHECK_SIDE_PANEL(title));
            if (side && side.found) {
                console.log(`  ok     "${title}"  [${wsName}]  (${side.how})`);
                continue;
            }

            const opened = await cdp.evaluate(OPEN_PANEL);
            if (opened !== 'opened' && opened !== 'already-open') {
                console.log(`  ?  "${title}"  [${wsName}]  — could not open Past Conversations (${opened})`);
                continue;
            }
            if (!(await cdp.evaluate(FOCUS_INPUT))) {
                console.log(`  ?  "${title}"  [${wsName}]  — search box vanished`);
                continue;
            }
            // A distinctive prefix is enough and avoids fuzzy-match noise on long titles.
            await typeText(cdp, title.slice(0, 24));
            await sleep(1500);

            const res = await cdp.evaluate(READ_RESULTS);
            if (res && res.error) {
                console.log(`  ?  "${title}"  [${wsName}]  — ${res.error}`);
            } else if (res.noItems) {
                console.log(`  STALE  "${title}"  [${wsName}]  channel ${row.channel_id} — gone from Antigravity; run /new in that channel`);
                stale += 1;
            } else {
                console.log(`  ok     "${title}"  [${wsName}]`);
            }
        } finally {
            await pressEscape(cdp);
            await sleep(300);
            cdp.close();
        }
    }

    if (stale) {
        console.log(`  ${stale} stale binding(s): restarting will NOT fix these — the channel needs /new`);
        process.exit(1);
    }
    console.log('  all bound sessions resolvable');
})();
