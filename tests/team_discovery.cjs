// Nearby-host UI uses synthetic announcements. UDP transport is checked separately in Python.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');const path=require('node:path');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});let browser;
 try{
  const ready=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(new Error('Fixture failed to start')),15000);child.stdout.on('data',data=>{text+=data;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]));}});child.on('error',reject);});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.request.post(ready.base+'/api/auth/login',{data:{username:'fixture',password:'fixture-only-password'}});
  await context.request.post(ready.base+'/team/projects',{data:{name:'Browser capture'}});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  let calls=0,payload={state:'ready',advertising:'needs_https',hosts:[
   {name:'Team Baton · Studio',address:'192.168.1.12:3004',url:'https://studio.local:8443'},
   {name:'Team Baton · Workshop',address:'192.168.1.14:3004',url:null},
   {name:'<img src=x onerror=alert(1)>',address:'192.168.1.15:3004',url:'javascript:alert(1)'}]};
  await page.route('**/team/discovery',route=>{calls++;return route.fulfill({json:payload});});
  await page.goto(ready.base+'/#team');await page.locator('#open-join').waitFor();assert.equal(calls,0,'Discovery belongs in the invitation, not below projects');
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/team/discovery')),page.locator('#open-join').click()]);assert.equal(calls,1,'Opening the invitation should discover hosts automatically');
  assert.equal(await page.locator('#nearby').evaluate(e=>e.closest('dialog').id),'join-dialog');assert.equal(await page.locator('#join-current-host').textContent(),ready.base);
  await page.locator('#find-servers').click();await page.locator('.nearby-host').nth(2).waitFor();
  async function rescan(){if(await page.locator('#find-servers').getAttribute('aria-expanded')==='true')await page.locator('#find-servers').click();await page.locator('#find-servers').click();}
  assert.equal(await page.locator('.nearby-host a').getAttribute('href'),'https://studio.local:8443/team.html?join=1');
  assert.equal(await page.locator('.nearby-host a').getAttribute('referrerpolicy'),'no-referrer');
  assert.equal(await page.locator('.nearby-host .badge').count(),2);assert.equal(await page.locator('.nearby-host img').count(),0);
  assert.match(await page.locator('#nearby-setup').textContent(),/HTTPS is needed/);
  const out=process.env.TEAM_DISCOVERY_SCREENSHOTS;if(out)fs.mkdirSync(out,{recursive:true});
  for(const theme of ['dark','light','oled']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);for(const width of [1440,390]){await page.setViewportSize({width,height:1000});await page.locator('#nearby').scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await page.locator('#nearby').evaluate(e=>getComputedStyle(e).borderBottomWidth),'0px');if(out){await page.screenshot({path:path.join(out,'nearby-'+theme+'-'+width+'.png'),fullPage:true});await page.locator('#find-servers').click();await page.locator('#join-dialog').screenshot({path:path.join(out,'invite-'+theme+'-'+width+'.png')});await page.locator('#find-servers').click();}}}
  payload={state:'ready',advertising:'local_only',hosts:[]};await rescan();await page.locator('#nearby-status').filter({hasText:'No nearby hosts found'}).waitFor();assert.equal(await page.locator('.nearby-host').count(),0);
  payload={state:'disabled',hosts:[]};await rescan();await page.locator('#nearby-status').filter({hasText:'discovery is off'}).waitFor();
  payload={state:'unavailable',advertising:'unavailable',hosts:[]};await rescan();await page.locator('#nearby-status').filter({hasText:'Could not search'}).waitFor();assert.match(await page.locator('#nearby-setup').textContent(),/45837/);
  await page.unroute('**/team/discovery');await page.route('**/team/discovery',route=>route.abort('failed'));await rescan();await page.locator('#nearby-status').filter({hasText:'Could not reach'}).waitFor();assert.equal(await page.locator('#find-servers').isEnabled(),true);
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('#nearby-results').evaluate(e=>getComputedStyle(e).animationName),'none');assert.equal(await page.locator('#join-dialog .code-character').count(),6);await page.keyboard.press('Escape');assert.equal(await page.locator('#join-dialog').evaluate(d=>d.open),false);
  assert.deepEqual(errors,[]);console.log('Integrated invitation discovery: automatic search, safe join links, no credential transfer, untrusted text, HTTPS-needed, disabled/empty/failure states and all themes/mobile OK');
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(error=>{console.error(error);process.exitCode=1;});
