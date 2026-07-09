---
name: verify
description: Drive the Maily frontend (Next.js) end-to-end to verify a change actually works, not just that it builds/lints.
---

# Maily frontend verify

Surface is GUI (browser). Six routes: `/`, `/storage`, `/login`, `/first-application`, `/settings`, `/cleanup-review`.

## Build/launch

```bash
cd development/frontend
pnpm install   # first time only
pnpm dev       # http://127.0.0.1:3000, Turbopack, hot-reload
```

If port 3000 is already in use, a dev server from a prior session is likely still running — reuse it (check `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/`) instead of killing it blind.

## Gotcha: the Playwright MCP tool is broken in this sandbox

`mcp__playwright__browser_navigate` (and any MCP Playwright tool) fails here with:

```
Error: async initializeServer: Target page, context or browser has been closed
...
exception while trying to kill process: Error: kill EPERM
```

This is the MCP wrapper failing to manage its own Chrome process (permission issue killing an already-running Chrome under `~/Library/Caches/ms-playwright-mcp/`), not a problem with Playwright itself. **Don't retry it more than once** — it's consistently broken, not transient.

**Workaround: run Playwright directly via a throwaway Node script**, bypassing the MCP wrapper's process lifecycle entirely:

```bash
cd <scratchpad>
npm init -y >/dev/null 2>&1
npm install playwright@1.61.1 --no-save   # chromium binary is usually already cached at
                                            # ~/Library/Caches/ms-playwright/chromium-*/
```

```js
// verify.mjs
import { chromium } from 'playwright'
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.goto('http://127.0.0.1:3000/storage', { waitUntil: 'networkidle' })
// ...drive it, then:
await browser.close()
```

```bash
node verify.mjs
```

This gives real click/keyboard-driven browser verification (not just curl'd SSR HTML) without touching the broken MCP tool.

## Curl-only fallback (structural check, no client-side interactivity)

When even the direct-Playwright path isn't worth setting up (e.g. checking a route just got wired up, not testing interaction): `curl -s http://127.0.0.1:3000/<route>` and grep the SSR HTML for expected classes/text. This proves the route renders and the server component tree is correct, but proves **nothing** about onClick/onChange/state — don't call it a PASS for interactive changes.

## Flows worth driving (found real bugs here before)

- **`/storage` tabs**: click "라벨" tab → `.list-pane .tl-head b` text changes from `[오늘, 내일, 이번 주]` to `[결제, 읽어볼 것]`. Scope the text-content check to `.list-pane` — the detail pane is always rendered alongside and will contain unrelated text (e.g. "오늘 09:12" from the static detail mock) that pollutes an unscoped `page.locator('text=...')` check. ArrowLeft/ArrowRight on a focused tab should also switch + move focus.
- **`/` DetailPane overflow**: click "이동 및 아카이브 더보기" → `.action-menu[data-open=true]`. Click "이동" menuitem → `.move-popover[data-open=true]` and action-menu closes. Click "다음부터도 여기로" → `.banner--info[data-show=true]` appears and popover closes.
- **`/settings` toggles**: click any `.toggle input` → `isChecked()` should flip. **This was broken once**: `.track`/`.knob` are absolutely-positioned siblings painted on top of the (opacity:0) checkbox input, so clicks landed on the decorative spans and never reached the input — `onChange` never fired for a real user. Fix is `pointer-events: none` on `.track` and `.knob` (both in `App.css` and the source mockup `design/boards/v1/current/09-settings.html`). If this regresses, check those two rules first before assuming the React state logic is wrong.
- Rapid double-click on the same toggle should net to the original state (no lost-update race).

## Mock-data caveat

Everything is static `*.mock.ts` data (no backend yet). "Does it fetch real data" isn't a valid check — verify rendering/interaction against the fixed mock values instead.
