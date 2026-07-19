#!/usr/bin/env node
/**
 * Real CDP liveness probe for Antigravity.
 *
 * The HTTP endpoints (/json/version, /json/list) are served by the BROWSER
 * process and keep answering even when every renderer is frozen (seen
 * 2026-07-18: the GPU process died on startup, all renderers blocked waiting
 * for a GPU channel, 12 page targets listed but Runtime.enable timed out on
 * every one — the bot then failed with "Timeout calling CDP method
 * Runtime.enable" while HTTP checks looked green).
 *
 * This probe attaches a WebSocket to EVERY workbench page and runs a real
 * Runtime.evaluate with a timeout. Exit code: 0 = all alive, 1 = any hung /
 * none found.
 *
 * Uses LazyGravity's own `ws` package (absolute path — CJS resolves relative
 * to this file's location, not cwd).
 */
const WebSocket = require('/home/chihmin/src/LazyGravity/node_modules/ws');

const PORT = process.env.CDP_PORT || '9223';
const TIMEOUT_MS = 8000;

async function probePage(pg) {
    return new Promise((resolve) => {
        let settled = false;
        const done = (v) => { if (!settled) { settled = true; try { ws.close(); } catch { } resolve(v); } };
        const ws = new WebSocket(pg.webSocketDebuggerUrl);
        ws.on('open', () => ws.send(JSON.stringify({
            id: 1, method: 'Runtime.evaluate',
            params: { returnByValue: true, expression: '1+1' },
        })));
        ws.on('message', (d) => { try { if (JSON.parse(d.toString()).id === 1) done(true); } catch { } });
        ws.on('error', () => done(false));
        setTimeout(() => done(false), TIMEOUT_MS);
    });
}

(async () => {
    let list;
    try {
        list = await (await fetch(`http://localhost:${PORT}/json/list`)).json();
    } catch (e) {
        console.log(`probe: cannot reach CDP http (${e.message})`);
        process.exit(1);
    }
    const pages = list.filter((p) => (p.url || '').includes('workbench.html'));
    if (pages.length === 0) {
        console.log('probe: no workbench pages found');
        process.exit(1);
    }
    let alive = 0, hung = 0;
    for (const pg of pages) {
        (await probePage(pg)) ? alive++ : hung++;
    }
    console.log(`probe: workbench pages=${pages.length} alive=${alive} hung=${hung}`);
    process.exit(hung === 0 ? 0 : 1);
})();
