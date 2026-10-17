// Real project health, bento layout, connection failure and recovery; synthetic data only.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');const path=require('node:path');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});let browser;
 try{
  const ready=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(new Error('Fixture failed to start')),15000);child.stdout.on('data',data=>{text+=data;if(text.includes('\n')){clearTimeout(timer);resolve(JSON.parse(text.split('\n')[0]));}});child.on('error',reject);});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.request.post(ready.base+'/api/auth/login',{data:{username:'fixture',password:'fixture-only-password'}});
  async function create(name,goals,archived=false){const response=await context.request.post(ready.base+'/team/projects',{data:{name}});assert.equal(response.status(),200);const project=await response.json();const update=await context.request.post(ready.base+'/team/'+project.id+'/settings',{data:{goals,archived}});assert.equal(update.status(),200);return project;}
  const design=await create('Design system','Keep tokens, real provider logos, and keyboard behavior consistent.');
  const archived=await create('Release archive','Decisions from the completed release, available to read.',true);
  const broken=await create('Storage check','A synthetic project with missing storage.');
  await create('Browser capture','Keep selected browser conversations in the shared project memory.');
  fs.unlinkSync(path.join(ready.dataRoot,'projects',broken.id,'project.db'));
  const response=await context.request.get(ready.base+'/team/projects');const data=await response.json();
  assert.equal(data.projects.find(p=>p.id===design.id).health.state,'running');assert.equal(data.projects.find(p=>p.id===archived.id).health.state,'paused');assert.equal(data.projects.find(p=>p.id===broken.id).health.state,'unavailable');
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(ready.base+'/#team');await page.locator('.project-entry').nth(4).waitFor();
  assert.equal(await page.locator('.project-entry[data-state=running]').count(),3);assert.equal(await page.locator('.project-entry[data-state=paused]').count(),1);assert.equal(await page.locator('.project-entry[data-state=unavailable]').count(),1);assert.equal(await page.locator('[data-project="'+broken.id+'"]').isDisabled(),true);
  const join=await page.locator('#open-join').boundingBox(),createBox=await page.locator('#new-project').boundingBox();assert(Math.abs(join.y-createBox.y)<2,'Join and New project must be alongside one another');
  const widths=await page.locator('.project-entry').evaluateAll(cards=>cards.map(card=>card.getBoundingClientRect().width));assert(widths[0]>widths[1],'Bento cards should have a clear wide/narrow rhythm');
  const out=process.env.TEAM_BENTO_SCREENSHOTS;if(out)fs.mkdirSync(out,{recursive:true});
  for(const theme of ['dark','light','oled']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);for(const width of [1440,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);if(out)await page.screenshot({path:path.join(out,'projects-'+theme+'-'+width+'.png'),fullPage:true});}}
  await page.locator('#open-join').click();await page.locator('#join-dialog').waitFor();await page.keyboard.press('Escape');
  await page.route('**/team/projects',route=>route.abort('failed'));await page.locator('#refresh-projects').click();await page.locator('#host-health').filter({hasText:'Host unreachable'}).waitFor();assert.equal(await page.locator('.project-entry[data-state=unavailable]').count(),5);assert.equal(await page.locator('.project-entry:disabled').count(),5);assert.match(await page.locator('#project-check-time').textContent(),/Last successful check/);
  await page.unroute('**/team/projects');await page.locator('#refresh-projects').click();await page.locator('#host-health').filter({hasText:'host reachable'}).waitFor();assert.equal(await page.locator('.project-entry[data-state=running]').count(),3);
  await context.request.post(ready.base+'/team/'+design.id+'/settings',{data:{archived:true}});
  await page.locator('[data-project="'+design.id+'"][data-state=paused]').waitFor({timeout:16000});
  await page.locator('[data-project="'+ready.project+'"]').click();await page.locator('#project-name').filter({hasText:'Relay engine'}).waitFor();
  assert.deepEqual(errors,[]);console.log('Team bento: measured green/yellow/red states, host-only summaries, layout, header actions, all themes, offline/recovery, live polling and project opening OK');
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(error=>{console.error(error);process.exitCode=1;});
