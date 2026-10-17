// Optional Chromium check for the illustration gallery and real PNG transparency.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const host=spawn(process.env.PYTHON || 'python3',[path.join(__dirname,'team_ui_host.py')],{stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const ready=await new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(new Error('Synthetic host did not start')),15000);host.stdout.on('data',data=>{output+=data;if(output.includes('\n')){clearTimeout(timeout);resolve(JSON.parse(output.split('\n')[0]));}});host.on('error',reject);});
    browser=await chromium.launch({headless:true,args:['--no-sandbox']});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(ready.base+'/assets/baton/index.html');await page.locator('figure').nth(12).waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('.preview img')].every(image=>image.complete&&image.naturalWidth));
    assert.equal(await page.locator('figure').count(),13);
    const alphas=await page.locator('.preview img').evaluateAll(images=>images.map(image=>{const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);return {file:image.getAttribute('src'),alpha:ctx.getImageData(0,0,1,1).data[3]};}));
    assert(alphas.every(image=>image.alpha===0),'Every illustration must have a truly transparent corner: '+JSON.stringify(alphas));
    for(const background of ['light','checker','dark']){await page.locator('button[data-background='+background+']').click();assert.equal(await page.locator('body').getAttribute('data-background'),background);}
    const zip=await page.request.get(ready.base+'/assets/baton/baton-collection.zip');assert.equal(zip.status(),200);
    const out=process.env.BATON_SCREENSHOTS;if(out){fs.mkdirSync(out,{recursive:true});await page.screenshot({path:path.join(out,'baton-collection.png'),fullPage:true});}
    await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    if(out)await page.screenshot({path:path.join(out,'baton-collection-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);console.log('Baton collection: 13 images loaded, transparent PNGs, background previews, ZIP and mobile layout OK');
  }finally{if(browser)await browser.close();host.kill('SIGINT');}
})().catch(error=>{console.error(error);process.exitCode=1;});
