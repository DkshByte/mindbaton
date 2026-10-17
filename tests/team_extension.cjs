// Durable MV3 project queue tests, using only Node's standard library.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');
let disk={},offline=false,failSave=false,lostAck=false,revoked=false,requests=0;
const saved=new Map();
function worker(){
 const context=vm.createContext({crypto:webcrypto,TextEncoder,URL,AbortSignal,Date,console,badge:()=>{},
  chrome:{storage:{local:{get:async defaults=>Object.fromEntries(Object.entries(defaults).map(([k,v])=>[k,structuredClone(disk[k]??v)])),
    set:async changes=>{if(failSave)throw new Error('Storage quota exceeded');Object.assign(disk,structuredClone(changes));}}},
    runtime:{onMessage:{addListener:()=>{}},onStartup:{addListener:()=>{}}},alarms:{create:()=>{},onAlarm:{addListener:()=>{}}}},
  fetch:async(url,options)=>{
   requests++;if(offline)throw new Error('offline');
   const ok=value=>({ok:true,status:200,json:async()=>value});
   if(revoked)return {ok:false,status:401,json:async()=>({error:'member revoked'})};
   if(url.endsWith('/view'))return ok({name:'Synthetic project',settings:{external:false}});
   if(url.includes('/context?'))return ok({text:'[team-baton]\nSynthetic discovery\n[/team-baton]',captured_at:Date.now()/1000,project_revision:2});
   const body=JSON.parse(options.body);assert(new TextEncoder().encode(options.body).length<1000000);
   for(const m of body.messages)saved.set(options.headers.Authorization+body.session_id+m.message_id+'@'+m.revision,m);
   if(lostAck){lostAck=false;throw new Error('lost ack after commit');}
   return ok({accepted:body.messages.map(m=>({message_id:m.message_id,revision:m.revision})),project_revision:2});
  }});
 vm.runInContext(fs.readFileSync('extension/team_background.js','utf8'),context);
 return context;
}
const drain=async()=>{for(let i=0;i<20;i++)await new Promise(setImmediate);};
(async()=>{
 let c=worker();
 const one=await c.teamMessage({action:'connect',host:'https://mindbaton.example.com',project:'a'.repeat(32),token:'tb_one'});
 const two=await c.teamMessage({action:'connect',host:'https://mindbaton.example.com',project:'a'.repeat(32),token:'tb_two'});
 assert.notEqual(one.scope,two.scope,'credential cache isolation');
 const url='https://chatgpt.com/c/selected';
 await c.teamMessage({action:'select',url,scope:one.scope});
 offline=true;
 const live={url,title:'Synthetic conversation',site:'chatgpt.com',turns:[{role:'user',text:'Original draft [team-baton]excluded[/team-baton]',sourceId:'user'}, {role:'assistant',text:'Completed discovery',sourceId:'assistant'}]};
 await c.teamCapture(live);await drain();
 assert.equal(disk.teamState.connections[one.scope].queue.length,1);
 assert.equal(disk.teamState.connections[two.scope].queue.length,0);
 assert(!JSON.stringify(disk.teamState.connections[one.scope].queue).includes('excluded'));
 c=worker();offline=false;lostAck=true;
 await c.teamMutate(s=>s.connections[one.scope].retryAt=0);await c.teamFlush();
 assert.equal(saved.size,2);assert.equal(disk.teamState.connections[one.scope].queue.length,1);
 await c.teamMutate(s=>s.connections[one.scope].retryAt=0);await c.teamFlush();
 assert.equal(saved.size,2);assert.equal(disk.teamState.connections[one.scope].queue.length,0);
 await c.teamCapture({...live,turns:[{role:'assistant',text:'Edited discovery',sourceId:'assistant'}]});await drain();
 assert.equal(saved.size,3);assert([...saved.values()].some(m=>m.revision===2&&m.content==='Edited discovery'));
 await c.teamMessage({action:'context',url,query:'task'});offline=true;
 assert((await c.teamMessage({action:'context',url,query:'task'})).text.includes('Context outdated; cached'));
 await c.teamMessage({action:'select',url,scope:two.scope});
 assert((await c.teamMessage({action:'context',url,query:'task'})).text.includes('no shared context available'));
 await c.teamMessage({action:'select',url,scope:one.scope});
 failSave=true;const before=JSON.stringify(disk);
 await assert.rejects(c.teamCapture({...live,turns:[{role:'user',text:'New pending draft',sourceId:'new'}]}),/quota/);
 assert.equal(JSON.stringify(disk),before,'quota failure must preserve previous pending work');failSave=false;
 await c.teamCapture({...live,turns:[{role:'user',text:'Pending while offline',sourceId:'offline'}]});await drain();
 offline=false;revoked=true;await c.teamMutate(s=>s.connections[one.scope].retryAt=0);await c.teamFlush();
 assert.equal(disk.teamState.connections[one.scope].stopped,'member revoked');
 const count=requests;await c.teamFlush();assert.equal(requests,count,'revocation stops retries');
 assert.equal(Object.keys(disk.teamState.connections[one.scope].cache).length,0);
 // Identical messages without site IDs still get separate identities for their occurrences.
 revoked=false;offline=true;
 await c.teamMessage({action:'select',url:'https://chatgpt.com/c/repeated',scope:two.scope});
 await c.teamCapture({url:'https://chatgpt.com/c/repeated',title:'Repeated',site:'chatgpt.com',turns:[{role:'user',text:'continue'},{role:'user',text:'continue'}]});await drain();
 const repeated=disk.teamState.connections[two.scope].queue[0].body.messages;
 assert.equal(repeated.length,2);assert.notEqual(repeated[0].message_id,repeated[1].message_id);
 // The initial new-chat binding follows the first concrete conversation URL once, then future new chats are Private.
 const root='https://chatgpt.com/';await c.teamMessage({action:'select',url:root,scope:two.scope});
 await c.teamMessage({action:'follow',from:root,url:'https://chatgpt.com/c/newly-created'});
 assert(disk.teamState.bindings['https://chatgpt.com/c/newly-created']);assert(!disk.teamState.bindings[root]);
 await c.teamMessage({action:'follow',from:'https://chatgpt.com/c/newly-created',url:'https://chatgpt.com/c/unselected'});
 assert(!disk.teamState.bindings['https://chatgpt.com/c/unselected']);
 console.log('Extension: credential isolation, durable restart, lost ACK, edits, cache fallback, quota protection, revocation and explicit binding OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
