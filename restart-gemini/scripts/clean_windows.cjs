#!/usr/bin/env node
/**
 * clean_windows.cjs — find (and optionally close) orphan blank Antigravity windows.
 *
 * Every Antigravity restart can leave behind windows that have no folder open and
 * an untouched "new chat" agent panel. They are useless to LazyGravity (the bot
 * routes by workspace, so a folder-less window can never serve a binding) but they
 * keep whole renderers alive — 32 of them were holding ~20 GB RSS on 2026-07-21.
 * That matters here because earlyoom SIGKILLs at 1.5 GB free during GPU jobs.
 *
 * A window is only treated as blank when ALL THREE hold:
 *   - document.title is exactly "Antigravity" — a window with a folder open is
 *     always "<folder> - Antigravity[ - <file>]", and the launcher is "Launchpad";
 *   - the Explorer has no root folders; and
 *   - the agent side panel still shows the empty-composer placeholder and carries
 *     almost no text (no conversation was ever started in it).
 * Anything that fails to answer CDP is left alone rather than guessed at.
 *
 * NB: do NOT try to read the workspace from the workbench URL — Antigravity
 * passes no `folder=` query param, so every window looks folder-less that way
 * (that false signal flagged the live `src` window on the first cut of this).
 *
 * Usage: node clean_windows.cjs [--close]     (default: dry run)
 *
 * Uses LazyGravity's own `ws` package (absolute path — CJS resolves relative
 * to this file's location, not cwd).
 */
const http = require('http');
const WebSocket = require('/home/chihmin/src/LazyGravity/node_modules/ws');

const PORT = process.env.CDP_PORT || '9223';
const CLOSE = process.argv.includes('--close');

// `raw: true` for endpoints that answer plain text — /json/close returns
// "Target is closing", not JSON, so parsing it would report a bogus failure
// on a close that actually worked.
const httpGet = (path, raw = false) =>
    new Promise((resolve, reject) => {
        http.get({ host: '127.0.0.1', port: PORT, path }, (res) => {
            let body = '';
            res.on('data', (c) => (body += c));
            res.on('end', () => {
                if (raw) return resolve(body.trim());
                try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
            });
        }).on('error', reject);
    });

function evaluate(wsUrl, expression, timeoutMs = 8000) {
    return new Promise((resolve) => {
        let settled = false;
        const done = (v) => { if (!settled) { settled = true; resolve(v); } };
        let sock;
        const timer = setTimeout(() => { try { sock && sock.close(); } catch {} done({ error: 'timeout' }); }, timeoutMs);
        try {
            sock = new WebSocket(wsUrl, { perMessageDeflate: false });
        } catch (e) {
            clearTimeout(timer);
            return done({ error: String(e) });
        }
        sock.on('open', () => sock.send(JSON.stringify({
            id: 1,
            method: 'Runtime.evaluate',
            params: { expression, returnByValue: true, awaitPromise: true },
        })));
        sock.on('message', (m) => {
            let d;
            try { d = JSON.parse(m); } catch { return; }
            if (d.id !== 1) return;
            clearTimeout(timer);
            try { sock.close(); } catch {}
            done(d.result && d.result.result ? d.result.result.value : { error: 'bad response' });
        });
        sock.on('error', (e) => { clearTimeout(timer); done({ error: String(e) }); });
    });
}

// Runs inside the page: classify this window as blank / real.
const CLASSIFY = `(() => {
    const panel = document.querySelector('.antigravity-agent-side-panel');
    const panelText = panel ? (panel.textContent || '').replace(/\\s+/g, ' ').trim() : '';
    const hasPlaceholder = /ask anything/i.test(panelText);
    return {
        title: document.title,
        explorerRoots: document.querySelectorAll('.explorer-folders-view .monaco-list-row').length,
        hasPanel: !!panel,
        panelLen: panelText.length,
        // an untouched composer: placeholder present, and nothing but chrome text around it
        looksEmptyChat: hasPlaceholder && panelText.length < 800,
    };
})()`;

(async () => {
    const targets = await httpGet('/json/list');
    const pages = targets.filter((p) => p.type === 'page' && /workbench/.test(p.url || ''));
    console.log(`workbench pages: ${pages.length}`);

    const blank = [];
    const keep = [];
    const unknown = [];

    for (const p of pages) {
        const info = await evaluate(p.webSocketDebuggerUrl, CLASSIFY);
        if (!info || info.error) {
            unknown.push({ p, why: (info && info.error) || 'no answer' });
            continue;
        }
        const isBlank =
            info.title === 'Antigravity' &&
            info.explorerRoots === 0 &&
            info.hasPanel &&
            info.looksEmptyChat;
        if (isBlank) blank.push({ p, info });
        else keep.push({ p, info });
    }

    for (const { p, info } of keep) {
        console.log(`  KEEP  ${p.title}   [explorer roots: ${info.explorerRoots}]`);
    }
    for (const { p, why } of unknown) {
        console.log(`  SKIP  ${p.title}  (unresponsive: ${why})`);
    }
    console.log(`  blank/orphan windows: ${blank.length}`);

    if (!blank.length) { console.log('nothing to clean'); return; }
    if (!CLOSE) { console.log('dry run — pass --close to actually close them'); return; }

    let closed = 0;
    for (const { p } of blank) {
        try {
            const reply = await httpGet(`/json/close/${p.id}`, true);
            if (/closing/i.test(reply)) closed += 1;
            else console.log(`  unexpected reply closing ${p.id}: ${reply}`);
        } catch (e) {
            console.log(`  failed to close ${p.id}: ${e}`);
        }
    }
    console.log(`closed ${closed}/${blank.length} blank windows`);
})();
