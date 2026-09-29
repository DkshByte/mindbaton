// Extra captures of the real app (demo.py data): "before" states for animation, a meaning search, and element boxes.
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'fs';
const OUT = process.argv[2], BASE = process.argv[3] || 'http://127.0.0.1:3005';
const b = await chromium.launch();
const c = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 3, colorScheme: 'dark' });
const p = await c.newPage();
const fix = () => p.addStyleTag({ content: `.wordmark > svg svg{display:none}` });
const box = (sel, rel) => p.evaluate(([sel, rel]) => {
  const r = document.querySelector(sel).getBoundingClientRect(), o = rel ? document.querySelector(rel).getBoundingClientRect() : { left: 0, top: 0 };
  return [r.left - o.left, r.top - o.top, r.width, r.height].map(v => Math.round(v * 10) / 10);
}, [sel, rel]);
const boxes = {};
await p.goto(BASE + '/');
await p.evaluate(async () => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'maya', password: 'demo-pass-123' }) }));
await p.reload(); await p.waitForTimeout(2500);
await p.evaluate(() => { location.hash = 'overview'; }); await p.waitForTimeout(2500); await fix(); await p.evaluate(() => scrollTo(0, 0));
boxes.kcards = await p.evaluate(() => [...document.querySelectorAll('#ov .kinds .kcard')].map(e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }));
const card = '#ov .ygrid section.card';
boxes.changed = await box(card);
boxes.chg = await p.evaluate(sel => {
  const c = document.querySelector(sel).getBoundingClientRect();
  return [...document.querySelectorAll(sel + ' .chg')].map(row => ['.was', '.now'].map(s => { const r = row.querySelector(s).getBoundingClientRect(); return [r.left - c.left, r.top - c.top, r.width, r.height]; }));
}, card);
await p.addStyleTag({ content: `#ov .kinds .kcard{visibility:hidden}` });
await p.waitForTimeout(200);
await p.screenshot({ path: `${OUT}/you_nokinds.png` });
await p.addStyleTag({ content: `#ov .chg .now{visibility:hidden} #ov .chg .was{text-decoration:none!important;color:var(--fg)!important}` });
await p.waitForTimeout(200);
await p.locator(card).first().screenshot({ path: `${OUT}/you_changed_before.png` });
// meaning search
await p.evaluate(() => { const q = 'what exercise do I do?'; document.querySelector('#q').value = q; recall(q, true); }); await p.waitForTimeout(1800);
await p.evaluate(() => scrollTo(0, 0));
await p.screenshot({ path: `${OUT}/ask_exercise.png` });
await p.locator('#recall .card').first().screenshot({ path: `${OUT}/ask_exercise_card.png` });
boxes.exerciseRows = await p.evaluate(() => { const c = document.querySelector('#recall .card').getBoundingClientRect(); return [...document.querySelectorAll('#recall .card .row')].map(e => { const r = e.getBoundingClientRect(); return [r.left - c.left, r.top - c.top, r.width, r.height]; }); });
boxes.dogSub = await p.evaluate(async () => { const q = "what's my dog's name?"; document.querySelector('#q').value = q; recall(q, true); await new Promise(r => setTimeout(r, 1500)); return document.querySelector('#recall .hello-sub')?.textContent; });
// chats: the hot card
await p.evaluate(() => { location.hash = 'chats'; }); await p.waitForTimeout(2000); await p.evaluate(() => scrollTo(0, 0));
boxes.hot = await box('#chats .pick.hot');
// the forget panel, both steps
await p.evaluate(() => { location.hash = 'overview'; }); await p.waitForTimeout(1500);
await p.evaluate(() => { document.querySelector('#q').value = ''; select(104); }); await p.waitForTimeout(1200);
boxes.panel = await box('#panel');
boxes.forgetBtn = await box('#panel [data-forget]', '#panel');
await p.locator('#panel [data-forget]').first().click(); await p.waitForTimeout(500);
boxes.forgetArmed = await box('#panel [data-forget]', '#panel');
fs.writeFileSync(`${OUT}/boxes.json`, JSON.stringify(boxes, null, 1));
await b.close();
console.log(JSON.stringify(boxes));
