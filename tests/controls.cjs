// Optional Chromium coverage for shared menus in the app and team shadow root.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');const path=require('node:path');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});let browser;
 try{
  const ready=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(new Error('Fixture did not start')),15000);child.stdout.on('data',data=>{out+=data;if(out.includes('\n')){clearTimeout(timer);resolve(JSON.parse(out.split('\n')[0]));}});child.on('error',reject);});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.request.post(ready.base+'/api/auth/login',{data:{username:'fixture',password:'fixture-only-password'}});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(ready.base+'/#team/'+ready.project);await page.locator('#project-name').filter({hasText:'Relay engine'}).waitFor();
  await page.locator('#tab-settings').click();const models=page.getByRole('combobox',{name:/Provider and model:/});await models.click();
  assert.equal(await page.locator('.mb-menu:popover-open [role=option]').count(),10);
  assert.equal(await page.locator('.mb-menu:popover-open [role=option] .mb-logo').count(),10);
  await models.press('End');await models.press('Enter');assert.match(await page.locator('#models').inputValue(),/claude-opus/);
  await page.getByRole('button',{name:'Save processing settings',exact:true}).click();await page.getByRole('status').filter({hasText:'Processing settings saved'}).waitFor();
  const saved=await context.request.get(ready.base+'/team/'+ready.project+'/view');assert.match((await saved.json()).settings.model,/claude-opus/);
  const out=process.env.CONTROL_SCREENSHOTS;if(out)fs.mkdirSync(out,{recursive:true});
  for(const theme of ['dark','light','oled']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});await models.scrollIntoViewIfNeeded();await models.click();await page.locator('.mb-menu:popover-open').waitFor();await page.waitForTimeout(250);assert.equal(await page.locator('.mb-menu:popover-open').isVisible(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(out)await page.screenshot({path:path.join(out,'model-'+theme+'-'+width+'.png')});
   await models.press('Escape');assert.equal(await models.getAttribute('aria-expanded'),'false');
  }}
  await page.setViewportSize({width:1440,height:1000});await page.locator('.nav [data-view=setup]').click();await page.locator('#t-ai').click();
  const provider=page.locator('#keyform').getByRole('combobox');await provider.click();await page.getByRole('option',{name:'Groq',exact:true}).click();
  assert.equal(await page.locator('#keyform select').inputValue(),'groq');
  let payload;await page.route('**/settings/ai-key',route=>{payload=route.request().postDataJSON();return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Fixture key rejected'})});});
  await page.locator('#keyform input[name=key]').fill('fixture-only-not-a-real-key');await page.locator('#keyform').getByRole('button',{name:'Test and save',exact:true}).click();await page.getByRole('status').filter({hasText:'Fixture key rejected'}).waitFor();
  assert.equal(payload.provider,'groq');assert.equal(await provider.isDisabled(),false);
  for(const logo of ['groq','openai','claude-color','gemini-color'])assert.equal((await context.request.get(ready.base+'/assets/icons/lh/'+logo+'.svg')).status(),200);
  await page.locator('.nav [data-view=team]').click();await page.locator('#tab-overview').click();await page.locator('#invite').click();await page.locator('#invite-code[data-code]').waitFor();
  assert.equal(await page.locator('.invite-character').count(),6);
  if(out){await page.screenshot({path:path.join(out,'invite-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'invite-mobile.png')});}
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await page.locator('.invite-character').first().evaluate(el=>getComputedStyle(el).animationName),'none');
  assert.deepEqual(errors,[]);console.log('Shared controls: model persistence, keyboard, real logos, Setup submission, all themes, mobile menus, invite boxes and reduced motion OK');
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(e=>{console.error(e);process.exitCode=1;});
