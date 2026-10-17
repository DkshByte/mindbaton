// Optional real-Chromium adapter checks. Uses a supplied Playwright installation, no runtime app dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/web-team.json')));
const content = fs.readFileSync(path.join(root, 'extension/content.js'), 'utf8');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'extension/manifest.json')));
const hosts = manifest.content_scripts[0].matches.map(url => new URL(url.replace('*','')).hostname);
assert.deepEqual(Object.keys(fixtures).sort(), hosts.sort(), 'every supported site must have a fixture');
(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox']});
  try {
    for (const [host, f] of Object.entries(fixtures)) {
      const page = await browser.newPage();
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      const composer = f.editable ? '<div id="prompt-textarea" contenteditable="true" role="textbox"></div>' : '<textarea id="userInput"></textarea>';
      const html = '<!doctype html><html><body>' + f.user.replace('USER','Original user message [team-baton]injected briefing[/team-baton]') +
        f.assistant.replace('ASSISTANT','A completed assistant discovery <div class="reasoning">secret reasoning</div><div data-testid="thinking-block">secret reasoning</div><div hidden>secret reasoning</div>') +
        '<form id="form">' + composer + '<button type="submit" '+ f.button + '>Send</button></form></body></html>';
      await page.route('**/*',route=>route.fulfill({status:200,contentType:'text/html',body:html}));
      await page.goto('https://'+host+'/c/synthetic-conversation');
      await page.evaluate(() => {
        window.teamTest={submits:[], captures:[],contextCalls:0,contextDelay:80,offline:false,shared:true,listeners:[]};
        const t=window.teamTest;
        window.chrome={runtime:{id:'synthetic-extension',getURL:p=>p,onMessage:{addListener:fn=>t.listeners.push(fn)},
          sendMessage:async m=>{
            if(m.team?.action==='status')return {selected:t.shared?'scope':''};
            if(m.team?.action==='context'){t.contextCalls++;await new Promise(r=>setTimeout(r,t.contextDelay));return t.shared ?
              {text:'[team-baton]\n'+(t.offline?'Host unreachable; no shared context available.':'Project discovery')+'\n[/team-baton]',outdated:t.offline}:{private:true};}
            if(m.live){t.captures.push(m.live);return {shared:true};}return null;
          }},storage:{local:{get:async defaults=>defaults},onChanged:{addListener:()=>{}}}};
        document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const el=document.querySelector('textarea,[contenteditable]');t.submits.push(el.value??el.innerText);});
      });
      await page.addScriptTag({content});
      const box=page.locator('textarea,[contenteditable]').first();
      await page.waitForTimeout(1650);
      const capture=await page.evaluate(()=>window.teamTest.captures[0]);
      assert(capture,host+': transcript capture missing');
      assert.deepEqual(capture.turns.map(t=>t.role),['user','assistant']);
      assert(!JSON.stringify(capture).includes('secret reasoning'),host+': hidden reasoning captured');
      assert(!JSON.stringify(capture).includes('injected briefing'),host+': injected context feedback');
      await box.fill('Keep this exact user draft.');
      await box.press('Enter');
      await page.waitForTimeout(200);
      let submits=await page.evaluate(()=>window.teamTest.submits);
      assert.equal(submits.length,1,host+': Enter did not submit exactly once');
      assert(submits[0].includes('Keep this exact user draft.')&&submits[0].includes('[team-baton]'),host+': draft or context missing');
      await box.fill('Click submission draft.');
      await page.locator('form button').click();
      await page.waitForTimeout(200);
      submits=await page.evaluate(()=>window.teamTest.submits);
      assert.equal(submits.length,2,host+': click duplicated or lost submission');
      assert(submits[1].includes('Click submission draft.'),host+': click lost draft');
      // Two rapid Enter presses share one context request and one submission.
      await box.fill('Double Enter draft.');
      await box.press('Enter');await box.press('Enter');await page.waitForTimeout(200);
      assert.equal(await page.evaluate(()=>window.teamTest.submits.length),3,host+': rapid Enter duplicated submission');
      await page.evaluate(()=>{window.teamTest.contextDelay=250;});
      await box.fill('Draft before edit.');await box.press('Enter');await box.fill('User edited while waiting.');await page.waitForTimeout(350);
      assert.equal(await page.evaluate(()=>window.teamTest.submits.length),3,host+': changed draft submitted');
      assert.equal(await box.innerText().catch(()=>''),f.editable?'User edited while waiting.':'');
      await page.evaluate(()=>{window.teamTest.offline=true;window.teamTest.contextDelay=20;});
      await box.fill('Offline draft.');await box.press('Enter');await page.waitForTimeout(100);
      submits=await page.evaluate(()=>window.teamTest.submits);
      assert.equal(submits.length,4,host+': outage blocked independent work');
      assert(submits[3].includes('no shared context available.')&&submits[3].includes('Offline draft.'));
      // Missing native send controls report unavailability and keep the draft.
      await page.locator('form button').evaluate(el=>el.remove());await box.fill('Fallback draft.');await box.press('Enter');await page.waitForTimeout(100);
      assert.equal(await page.evaluate(()=>window.teamTest.submits.length),4);
      assert((await page.locator('body').innerText()).includes('Automatic project context unavailable'));
      assert.deepEqual(errors,[],host+': page errors');
      console.log(host+': capture, Enter, click, rapid Enter, edited draft, outage and fallback OK');
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
