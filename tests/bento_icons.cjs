// Real bento rendering and asset loading with an isolated server and fictional memories.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const host=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});let browser;
 try{
  const ready=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(new Error('Synthetic host did not start')),15000);host.stdout.on('data',data=>{output+=data;if(output.includes('\n')){clearTimeout(timer);resolve(JSON.parse(output.split('\n')[0]));}});host.on('error',reject);});
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  assert.equal((await context.request.post(ready.base+'/api/auth/login',{data:{username:'fixture',password:'fixture-only-password'}})).status(),200);
  for(const [text,rel,entity] of [
   ["I'm Maya, a product designer.",'is','product designer'],['I live in Lisbon.','lives in','Lisbon'],
   ["I'm working on Pantry.",'working on','Pantry'],['I use Figma.','uses','Figma'],['I have a camera.','has','camera'],
   ["I'm learning Portuguese.",'learning','Portuguese'],['I like specialty coffee.','likes','specialty coffee'],
   ['I dislike clutter.','dislikes','clutter'],['I want to run a half marathon.','wants','run a half marathon'],
   ['Context archive is connected to my memory.','connected to','Context archive']
  ])assert.equal((await context.request.post(ready.base+'/remember',{data:{text,relations:[['me',rel,entity]]}})).status(),200);
  assert.equal((await context.request.post(ready.base+'/remember',{data:{text:'My friend Ana is a designer.'}})).status(),200);
  const page=await context.newPage(),errors=[],assetErrors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/assets/icons/generated/')&&r.status()>=400)assetErrors.push(r.url()+': '+r.status());});
  await page.goto(ready.base+'/#overview');await page.locator('.kcard .bento-icon').nth(10).waitFor();
  const expected=['who','place','project','tool','own','learn','like','dislike','people','want','other'];
  assert.deepEqual(await page.locator('.kcard .bento-icon').evaluateAll(images=>images.map(i=>i.getAttribute('src').split('/').pop().replace('.webp',''))),expected);
  await page.waitForFunction(()=>[...document.querySelectorAll('.kcard img')].every(i=>i.complete&&i.naturalWidth));
  assert.equal(await page.locator('.kcard .wm img').count(),11);
  assert.equal(await page.locator('.kcard img:not([alt=""])').count(),0);
  const out=process.env.BENTO_ICON_SCREENSHOTS;if(out)fs.mkdirSync(out,{recursive:true});
  for(const theme of ['dark','light','oled'])for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
   await page.evaluate(()=>scrollTo(0,0));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,theme+' '+width);
   if(out)await page.screenshot({path:path.join(out,'bento-'+theme+'-'+width+'.png'),fullPage:true});
  }
  await page.locator('.kcard.who .chip').first().click();await page.locator('#panel').waitFor({state:'visible'});
  await page.goto(ready.base+'/assets/icons/generated/index.html');
  await page.waitForFunction(()=>[...document.querySelectorAll('img')].filter(i=>i.loading!=='lazy').every(i=>i.complete&&i.naturalWidth));
  assert.equal(await page.locator('.asset').count(),11);
  await page.getByRole('button',{name:'Light',exact:true}).click();assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  await page.getByRole('button',{name:'24px',exact:true}).click();assert.equal(await page.locator('body').getAttribute('data-size'),'24');
  assert.equal((await context.request.get(ready.base+'/assets/icons/generated/mindbaton-bento-icons.zip')).status(),200);
  assert.deepEqual(assetErrors,[]);assert.deepEqual(errors,[]);
  console.log('Bento icons: 11 generated assets, real cards, click-through, dark/light/OLED, desktop/mobile, gallery and ZIP OK');
 }finally{if(browser)await browser.close();host.kill('SIGINT');}
})().catch(error=>{console.error(error);process.exitCode=1;});
