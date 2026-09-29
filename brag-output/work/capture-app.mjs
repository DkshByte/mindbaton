import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const OUT = process.argv[2], DPR = 3;
const b = await chromium.launch();
const mk = async () => { const c = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: DPR, colorScheme: 'dark' }); return [c, await c.newPage()]; };
const FIX = `.wordmark > svg svg{display:none}`; // app bug: .wordmark svg also sizes the nested mark
const fix = async p => { await p.addStyleTag({ content: FIX }); };
const shot = (p, name) => p.screenshot({ path: `${OUT}/${name}.png` });
const el = async (p, sel, name) => { const l = p.locator(sel).first(); await l.scrollIntoViewIfNeeded(); await l.screenshot({ path: `${OUT}/${name}.png` }); };
const view = async (p, v, wait = 1800) => { await p.evaluate(v => { location.hash = v; }, v); await p.waitForTimeout(wait); await fix(p); await p.evaluate(() => scrollTo(0, 0)); };
const ask = async (p, q) => { await p.evaluate(q => { document.querySelector('#q').value = q; recall(q, true); }, q); await p.waitForTimeout(1800); await fix(p); };

// signed-out gate (profile tiles)
{ const [c, p] = await mk(); await p.goto('http://127.0.0.1:3005/'); await p.waitForTimeout(2500); await shot(p, 'gate'); await c.close(); }

const [c, p] = await mk();
p.on('pageerror', e => console.log('pageerror', e.message));
await p.goto('http://127.0.0.1:3005/');
await p.evaluate(async () => fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'maya', password: 'demo-pass-123' }) }));
await p.reload(); await p.waitForTimeout(3000);

await view(p, 'overview', 2500);
await shot(p, 'you');
await el(p, '#ov .hero', 'you_hero');
await el(p, '#ov .stats', 'you_stats');
const nk = await p.locator('#ov .kinds .kcard').count();
for (let i = 0; i < nk; i++) await p.locator('#ov .kinds .kcard').nth(i).screenshot({ path: `${OUT}/kcard_${i}.png` });
await el(p, '#ov .kinds', 'you_kinds');
await p.locator('#ov .ygrid').first().locator('section.card').nth(0).screenshot({ path: `${OUT}/you_changed.png` });
await p.locator('#ov .ygrid').first().locator('section.card').nth(1).screenshot({ path: `${OUT}/you_try.png` });
await p.evaluate(() => scrollTo(0, 0));

for (const [q, n] of [['where do I live?', 'ask_live'], ['how do I take my coffee?', 'ask_coffee'], ["what's my dog's name?", 'ask_dog'], ['what am I building?', 'ask_build']]) {
  await ask(p, q); await p.evaluate(() => scrollTo(0, 0)); await shot(p, n);
  if (await p.locator('#recall .answer').count()) await el(p, '#recall .answer', n + '_answer');
  if (await p.locator('#recall .card').count()) await el(p, '#recall .card', n + '_card');
}

await view(p, 'chats'); await shot(p, 'chats');
if (await p.locator('#chats .pick.hot').count()) await el(p, '#chats .pick.hot', 'chats_hot');
await p.evaluate(() => scrollTo(0, 0));
await p.evaluate(() => select(8)); await p.waitForTimeout(1200); await fix(p);
await shot(p, 'chat8'); await el(p, '#panel', 'chat8_panel');
await p.keyboard.press('Escape'); await p.waitForTimeout(600);

await view(p, 'topics'); await shot(p, 'topics');
const nt = await p.locator('#topics .tcard').count();
for (let i = 0; i < Math.min(nt, 10); i++) await p.locator('#topics .tcard').nth(i).screenshot({ path: `${OUT}/tcard_${i}.png` });
await p.evaluate(() => scrollTo(0, 0));

await view(p, 'map', 5000); await shot(p, 'map');

await view(p, 'setup', 2500);
await p.evaluate(() => {
  const w = document.createTreeWalker(document.querySelector('#setup'), NodeFilter.SHOW_TEXT);
  const kill = [];
  while (w.nextNode()) { const n = w.currentNode;
    if (/Will try again|URLError|urlopen/.test(n.textContent)) kill.push(n.parentElement);
    n.textContent = n.textContent.replace(/https?:\/\/127\.0\.0\.1:3005/g, 'http://192.168.1.20:3004'); }
  kill.forEach(e => e && (e.style.display = 'none'));
});
await p.waitForTimeout(300);
await shot(p, 'setup');
if (await p.locator('#setup .feat').count()) { const n = await p.locator('#setup .feat').count(); for (let i = 0; i < n; i++) await p.locator('#setup .feat').nth(i).screenshot({ path: `${OUT}/setup_feat_${i}.png` }); }
await p.evaluate(() => scrollTo(0, 0));

await view(p, 'overview', 1500);
await p.evaluate(() => select(104)); await p.waitForTimeout(1200); await fix(p);
await shot(p, 'mem104'); await el(p, '#panel', 'mem104_panel');
await p.locator('#panel [data-forget]').first().click(); await p.waitForTimeout(500);
await shot(p, 'mem104_armed'); await el(p, '#panel', 'mem104_panel_armed');
await b.close();
console.log('done');
