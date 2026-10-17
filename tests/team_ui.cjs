// End-to-end host and invited-teammate UI check; uses only synthetic project data.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const child=spawn(process.env.PYTHON || 'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});
 let browser;
 try {
  const ready=await new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>reject(new Error('Synthetic host failed to start')),15000);let output='';
   child.stdout.on('data',chunk=>{output+=chunk;if(output.includes('\n')){clearTimeout(timeout);try{resolve(JSON.parse(output.split('\n')[0]));}catch(e){reject(e);}}});
   child.on('error',error=>{clearTimeout(timeout);reject(error);});
   child.on('exit',code=>{clearTimeout(timeout);if(!output)reject(new Error('Synthetic host exited '+code));});
  });
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const context=await browser.newContext();const login=await context.request.post(ready.base+'/api/auth/login',{data:{username:'fixture',password:'fixture-only-password'}});assert.equal(login.status(),200);
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const url=ready.base+'/#team/'+ready.project;
  await page.goto(ready.base+'/team.html?project='+ready.project);await page.waitForURL(url);await page.locator('#project-name').filter({hasText:'Relay engine'}).waitFor();
  await page.locator('#tab-settings').click();await page.locator('#usage').filter({hasText:'Estimated project use this month: $0.0000'}).waitFor();
  await page.locator('#goals-form textarea').fill('Keep this unsaved goal');await page.locator('#tab-overview').click();await page.waitForTimeout(10500);await page.locator('#tab-settings').click();assert.equal(await page.locator('#goals-form textarea').inputValue(),'Keep this unsaved goal');await page.locator('#tab-overview').click();
  assert.equal(await page.locator('#notice.error').count(),0,'caught UI errors must fail verification');
  await page.locator('#briefing').click();await page.locator('#context').filter({hasText:'saves revisions'}).waitFor();
  await page.locator('#context-dialog [data-close]').click();
  await page.locator('#invite').click();await page.locator('#invite-code[data-code]').waitFor();assert.equal(await page.locator('#invite-code .invite-character').count(),6);
  const code=await page.locator('#invite-code').getAttribute('data-code');await page.locator('#invite-dialog [data-close]').click();
  const invited=await browser.newContext();const member=await invited.newPage();member.on('pageerror',e=>errors.push(e.message));
  await member.goto(ready.base+'/team.html?join=1');await member.locator('#join-dialog').waitFor();
  await member.locator('#join input[name=name]').fill('Rui');
  const boxes=member.locator('.code-character');assert.equal(await boxes.count(),6);
  await boxes.first().focus();await member.keyboard.type('ab3cd4');assert.equal(await member.locator('#join input[name=code]').inputValue(),'AB3CD4');
  await boxes.nth(5).press('Backspace');await boxes.nth(5).press('Backspace');assert.equal(await boxes.nth(4).inputValue(),'');
  await boxes.first().fill('a');await boxes.nth(1).focus();await member.keyboard.type('@_!é');assert.equal(await boxes.nth(1).inputValue(),'B');
  const paste=async text=>boxes.first().evaluate((box,text)=>{const data=new DataTransfer();data.setData('text/plain',text);box.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));},text);
  const before=await member.locator('#join input[name=code]').inputValue();await paste('ABC_234');assert.equal(await member.locator('#join input[name=code]').inputValue(),before);
  await paste(code.toLowerCase());assert.equal(await member.locator('#join input[name=code]').inputValue(),code.replace('-',''));
  if(process.env.TEAM_SCREENSHOTS){const fs=require('node:fs');fs.mkdirSync(process.env.TEAM_SCREENSHOTS,{recursive:true});for(const width of [1440,390]){await member.setViewportSize({width,height:844});assert.equal(await member.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await member.screenshot({path:path.join(process.env.TEAM_SCREENSHOTS,'team-join-'+width+'.png'),fullPage:true});}}
  await member.locator('#join button').click();
  await member.locator('#join-status').filter({hasText:'Waiting for host approval'}).waitFor();
  await page.reload();await page.locator('#overview-approval').filter({hasText:'1 join request'}).click();await page.locator('#pending button').filter({hasText:'Approve'}).click();
  await member.waitForURL(ready.base+'/team.html?join=1&project='+ready.project);await member.locator('#project-name').filter({hasText:'Relay engine'}).waitFor();
  assert.equal(await member.locator('#host-controls').isVisible(),false);
  assert.equal(await member.locator('#notice.error').count(),0);
  await member.locator('#publish-open').click();
  await member.locator('#publish textarea[name=content]').fill('Reported progress: client queue survived restart.');
  await member.getByRole('combobox',{name:/Update type/}).click();await member.getByRole('option',{name:'Reported progress',exact:true}).click();await member.getByRole('button',{name:'Publish update',exact:true}).click();
  await member.locator('#updates').filter({hasText:'client queue survived restart'}).waitFor();
  await page.reload();await page.locator('#updates').filter({hasText:'client queue survived restart'}).waitFor();
  assert.equal(await page.locator('#notice.error').count(),0);
  assert.match(await page.locator('#brief-coverage').textContent(),/1 shared conversation/);assert.match(await page.locator('#overview-names').textContent(),/Rui/);await page.locator('#recent-conversations .conversation-title').click();await page.locator('#sources').filter({hasText:'saves revisions'}).waitFor();await page.locator('#sources-dialog [data-close]').click();
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
   await page.setViewportSize(viewport);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }
  await page.setViewportSize({width:1440,height:1000});
  const documentId=await page.evaluate(()=>window.teamDocumentId='same-document');
  await page.locator('.nav [data-view=chats]').click();await page.locator('.nav [data-view=team]').click();
  assert.equal(await page.evaluate(()=>window.teamDocumentId),documentId,'sidebar navigation must keep the same document');
  await page.locator('#tab-overview').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#tab-conversations').getAttribute('aria-selected'),'true');
  await page.locator('#search').fill('queue');await page.locator('#search').press('Enter');await page.locator('#search-results').filter({hasText:'saves revisions'}).waitFor();
  await page.locator('#tab-overview').click();
  await page.locator('#connect-open').click();await page.locator('[data-client=browser]').click();assert.equal(await page.locator('[data-client=browser]').getAttribute('aria-pressed'),'true');await page.locator('#connect-dialog [data-close]').click();
  for(const theme of ['light','oled','dark']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
  const screenshotDir=process.env.TEAM_SCREENSHOTS;
  if(screenshotDir){const fs=require('node:fs');fs.mkdirSync(screenshotDir,{recursive:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(screenshotDir,'team-mobile.png'),fullPage:true});await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(screenshotDir,'team-desktop.png'),fullPage:true});}
  await page.locator('#all-projects').click();await page.locator('#projects .project-entry').filter({hasText:'Relay engine'}).click();await page.locator('#project-name').filter({hasText:'Relay engine'}).waitFor();
  await page.locator('#tab-settings').click();await page.locator('#archive').click();await page.locator('#confirm-action').click();await page.locator('#project-state').filter({hasText:'Archived'}).waitFor();
  assert.equal(await page.locator('#publish-open').isDisabled(),true);
  const created=await context.request.post(ready.base+'/team/projects',{data:{name:'Fresh project'}});assert.equal(created.status(),200);
  await page.locator('#all-projects').click();await page.locator('#project-total').filter({hasText:'2 projects'}).waitFor();
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'team-projects.png'),fullPage:true});
  await page.locator('#projects .project-entry').filter({hasText:'Fresh project'}).click();await page.locator('#first-steps').waitFor();
  assert.equal(await page.locator('#setup-steps .setup-step').count(),3);assert.match(await page.locator('#brief-coverage').textContent(),/0 shared conversations/);
  if(screenshotDir)await page.screenshot({path:path.join(screenshotDir,'team-empty-project.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('Team UI: host usage display, invitation/approval, project-only teammate, shared publication, archive and desktop/mobile layout OK');
 }finally{if(browser)await browser.close();child.kill('SIGINT');}
})().catch(e=>{console.error(e);process.exitCode=1;});
