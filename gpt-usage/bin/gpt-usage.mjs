#!/usr/bin/env node
/**
 * gpt-usage — show ChatGPT/Codex (openai-codex) subscription rate-limit usage.
 *
 * Reads the OAuth token pi stored in ~/.pi/agent/auth.json (provider "openai-codex"),
 * refreshes it if expired, then makes one minimal request to the Codex responses
 * endpoint and reads the X-Codex-* rate-limit headers off the response. The request
 * is aborted as soon as headers arrive, so it costs ~no quota (and on a 429 it costs
 * none at all). No dependency on the `codex` CLI.
 *
 * Usage: node gpt-usage.mjs [--json] [--model gpt-5.5]
 */
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const AUTH_PATH = join(homedir(), ".pi/agent/auth.json");
const CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
const TOKEN_URL = "https://auth.openai.com/oauth/token";
const RESP_URL = "https://chatgpt.com/backend-api/codex/responses";
const JWT_CLAIM = "https://api.openai.com/auth";

const args = process.argv.slice(2);
const asJson = args.includes("--json");
const model = (args[args.indexOf("--model") + 1] && args.includes("--model")) ? args[args.indexOf("--model") + 1] : "gpt-5.5";

function die(msg) { console.error(msg); process.exit(1); }

function decodeAccountId(access) {
  try {
    const p = JSON.parse(Buffer.from(access.split(".")[1], "base64").toString("utf8"));
    return p?.[JWT_CLAIM]?.chatgpt_account_id || null;
  } catch { return null; }
}

let store;
try { store = JSON.parse(readFileSync(AUTH_PATH, "utf8")); }
catch { die(`Cannot read ${AUTH_PATH} — is pi logged into ChatGPT? Run pi → /login (ChatGPT Plus/Pro).`); }

let cred = store["openai-codex"];
if (!cred || cred.type !== "oauth" || !cred.access) {
  die("No openai-codex OAuth credentials in auth.json. Run pi → /login and pick ChatGPT Plus/Pro (Codex).");
}

// Refresh if expiring within 60s
if (typeof cred.expires === "number" && Date.now() >= cred.expires - 60_000) {
  try {
    const r = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: cred.refresh, client_id: CLIENT_ID }),
    });
    if (r.ok) {
      const j = await r.json();
      if (j.access_token && j.refresh_token && typeof j.expires_in === "number") {
        cred = { type: "oauth", access: j.access_token, refresh: j.refresh_token,
                 expires: Date.now() + j.expires_in * 1000,
                 accountId: decodeAccountId(j.access_token) || cred.accountId };
        store["openai-codex"] = cred;
        writeFileSync(AUTH_PATH, JSON.stringify(store, null, 2));
      }
    }
  } catch { /* fall through with existing token */ }
}

const accountId = cred.accountId || decodeAccountId(cred.access);
const headers = {
  "Authorization": `Bearer ${cred.access}`,
  "chatgpt-account-id": accountId,
  "originator": "pi",
  "OpenAI-Beta": "responses=experimental",
  "content-type": "application/json",
  "accept": "text/event-stream",
  "User-Agent": "pi (linux)",
};
const body = JSON.stringify({
  model, instructions: "",
  input: [{ type: "message", role: "user", content: [{ type: "input_text", text: "hi" }] }],
  stream: true, store: false,
});

const ctrl = new AbortController();
let res;
try {
  res = await fetch(RESP_URL, { method: "POST", headers, body, signal: ctrl.signal });
} catch (e) { die(`Request failed: ${e.message}`); }
// We only need headers — abort the body stream immediately to avoid spending quota.
ctrl.abort();

const h = (k) => res.headers.get(k);
const num = (k) => { const v = h(k); return v == null ? null : Number(v); };

const data = {
  plan: h("x-codex-plan-type"),
  activeLimit: h("x-codex-active-limit"),
  credits: { balance: num("x-codex-credits-balance"), hasCredits: h("x-codex-credits-has-credits"), unlimited: h("x-codex-credits-unlimited") },
  primary: {
    usedPercent: num("x-codex-primary-used-percent"),
    windowMinutes: num("x-codex-primary-window-minutes"),
    resetAt: num("x-codex-primary-reset-at"),
    resetAfterSeconds: num("x-codex-primary-reset-after-seconds"),
  },
  secondary: {
    usedPercent: num("x-codex-secondary-used-percent"),
    windowMinutes: num("x-codex-secondary-window-minutes"),
    resetAt: num("x-codex-secondary-reset-at"),
    resetAfterSeconds: num("x-codex-secondary-reset-after-seconds"),
  },
  httpStatus: res.status,
};

if (data.primary.usedPercent == null && data.secondary.usedPercent == null) {
  if (asJson) { console.log(JSON.stringify({ error: "no rate-limit headers", httpStatus: res.status }, null, 2)); }
  else { console.error(`No X-Codex-* headers returned (HTTP ${res.status}). Token may be invalid — try pi → /login again.`); }
  process.exit(2);
}

if (asJson) { console.log(JSON.stringify(data, null, 2)); process.exit(0); }

// Pretty Chinese output, Taiwan time (UTC+8)
const tw = (epoch) => epoch ? new Date(epoch * 1000).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false }) : "—";
const dur = (s) => {
  if (s == null) return "—";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} 分鐘`;
  const hh = Math.floor(m / 60), mm = m % 60;
  return `${hh} 小時 ${mm} 分`;
};
const bar = (pct) => {
  if (pct == null) return "";
  const n = Math.max(0, Math.min(10, Math.round(pct / 10)));
  return "█".repeat(n) + "░".repeat(10 - n);
};
const win = (mins) => mins == null ? "?" : (mins % 1440 === 0 ? `${mins / 1440} 天` : (mins % 60 === 0 ? `${mins / 60} 小時` : `${mins} 分`));

const P = data.primary, S = data.secondary;
const lines = [];
lines.push(`🤖 ChatGPT/Codex 用量  (方案: ${data.plan ?? "?"}${data.activeLimit ? " / " + data.activeLimit : ""})`);
lines.push("");
lines.push(`🟠 短窗 (${win(P.windowMinutes)} 滾動)`);
lines.push(`   已用 ${P.usedPercent}%  剩 ${P.usedPercent == null ? "—" : 100 - P.usedPercent}%   ${bar(P.usedPercent)}`);
lines.push(`   重置: ${tw(P.resetAt)} (還有 ${dur(P.resetAfterSeconds)})`);
lines.push("");
lines.push(`🔵 長窗 (${win(S.windowMinutes)})`);
lines.push(`   已用 ${S.usedPercent}%  剩 ${S.usedPercent == null ? "—" : 100 - S.usedPercent}%   ${bar(S.usedPercent)}`);
lines.push(`   重置: ${tw(S.resetAt)} (還有 ${dur(S.resetAfterSeconds)})`);
if (data.credits.balance != null) {
  lines.push("");
  lines.push(`💳 額外 credits: ${data.credits.balance}${data.credits.unlimited === "True" ? " (unlimited)" : ""}`);
}
if (res.status === 429) lines.push("\n⚠️ 目前短窗已達上限 (429)，要等重置或換模型/本機 qwen。");
console.log(lines.join("\n"));
