/* Team Baton mounts into the native app view or the project-only invitation page. No personal graph is used. */
window.TeamBaton = (() => {
  const LABELS = {progress:'Reported progress', discovery:'Discovery', proposal:'Proposal', decision:'Agreed decision', blocker:'Blocker', handoff:'Handoff', correction:'Correction'};
  const uid = () => crypto.randomUUID?.() || [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('');
  function icon(name) {
    const template = document.createElement('template');
    template.innerHTML = MindbatonIcons[name] || MindbatonIcons.message;
    return template.content.firstElementChild;
  }
  let templatePromise;
  async function open(host, options={}) {
    if (host.teamBaton) return host.teamBaton;
    templatePromise ||= fetch('/team.html').then(r=>{if(!r.ok)throw new Error('Could not load Team Baton. Refresh and try again.');return r.text();}).then(html=>new DOMParser().parseFromString(html,'text/html').getElementById('team-template')).catch(error=>{templatePromise=undefined;throw error;});
    return mount(host, await templatePromise, options);
  }
  function mount(host, template, options={}) {
    if (host.teamBaton) return host.teamBaton;
    const root = host.attachShadow({mode:'open'});
    host.toggleAttribute('data-embedded',!!options.embedded);
    root.append(template.content.cloneNode(true));
    MindbatonControls.install(root);
    const $ = id => root.getElementById(id);
    const all = selector => [...root.querySelectorAll(selector)];
    let pid = options.project || new URLSearchParams(location.search).get('project');
    let canManageProjects=false,projectsCheckedAt=0,projectsPending=false,nearbyPending=false;
    let view, projects=[], tab='overview', contextData, contextPid, selectedClient='codex', inviteCode='', pollTimer, toastTimer, draftId, showAllUpdates=false;
    const node = (tag,text,parent,cls) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;if(parent)parent.append(el);return el;};
    const decorate = scope => scope.querySelectorAll('[data-icon]').forEach(el=>{el.prepend(icon(el.dataset.icon));el.removeAttribute('data-icon');});
    const button = (text,parent,fn,cls='btn quiet small',symbol) => {const el=node('button',text,parent,cls);el.type='button';if(symbol)el.prepend(icon(symbol));el.addEventListener('click',()=>action(fn));return el;};
    const names = () => Object.fromEntries([['host','Host'],['ai','AI'],...(view?.members||[]).map(m=>[m.id,m.name])]);
    const whoName = id => names()[id] || (String(id).startsWith('host:')?'Host':'Teammate');
    function relative(ts) {if(!ts)return 'Never connected';const seconds=Math.max(0,(Date.now()/1000-ts));return seconds<60?'just now':seconds<3600?Math.floor(seconds/60)+'m ago':seconds<86400?Math.floor(seconds/3600)+'h ago':seconds<604800?Math.floor(seconds/86400)+'d ago':new Date(ts*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'});}
    function badge(text,parent,cls='') {return node('span',text,parent,'badge '+cls);}
    function notify(text,error=false) {if(error)$('loading').hidden=true;$('notice').textContent=text;$('notice').classList.toggle('error',error);}
    function toast(text) {clearTimeout(toastTimer);$('toast').textContent=text;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,3200);}
    async function api(path, body, signal) {
      const r=await fetch(path,{signal,method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
      const d=await r.json();if(!r.ok){const error=new Error(d.error || 'Request failed. Try again.');error.status=r.status;throw error;}return d;
    }
    const projectAPI = (action,body) => api('/team/'+pid+'/'+action,body);
    async function action(fn) {
      const dialog=root.querySelector('dialog[open]');if(dialog)dialog.querySelector('.dialog-error').textContent='';
      try {await fn();} catch(e) {const current=root.querySelector('dialog[open]');if(current)current.querySelector('.dialog-error').textContent=e.message;else notify(e.message,true);}
    }
    function showDialog(id) {const dialog=$(id);dialog.querySelector('.dialog-error').textContent='';if(!dialog.open)dialog.showModal();if(id==='join-dialog'){$('join-current-host').textContent=location.origin;loadNearby();}}
    function setTab(next, focus=false) {
      tab=next;
      all('[data-tab]').forEach(b=>{const current=b.dataset.tab===next;b.setAttribute('aria-selected',String(current));b.tabIndex=current?0:-1;if(current&&focus)b.focus();});
      all('.tab-panel').forEach(panel=>panel.hidden=panel.id!=='view-'+next);
    }
    function logo(name,parent) {
      const lower=String(name||'').toLowerCase();const providerLogo=MindbatonControls.logo(name);if(providerLogo){parent.append(providerLogo);return;}
      const file=/codex/.test(lower)?'codex-color.svg':/claude/.test(lower)?'claudecode-color.svg':/chatgpt|openai/.test(lower)?'openai.svg':null;
      if(file){const img=node('img',undefined,parent);img.src='/assets/icons/lh/'+file;img.alt='';}else parent.append(icon(/browser|extension/.test(lower)?'browser':'plug'));
    }
    function empty(parent,title,description,cta) {
      const box=node(parent.tagName==='UL'?'li':'div',undefined,parent,'empty');
      const asset={clients:'/assets/baton/connect.png',projects:'/assets/team/baton-together.png',conversations:'/assets/baton/no-chats.png','recent-conversations':'/assets/baton/no-chats.png',updates:'/assets/baton/first-memory.png'}[parent.id];
      if(asset){const art=node('img',undefined,box,'empty-art');art.src=asset;art.alt='';art.width=120;art.height=96;}else box.append(icon('plug'));
      node('h3',title,box);node('p',description,box);if(cta&&!view?.archived)button(cta.label,box,cta.fn,'btn','plus');
    }
    async function copy(text) {
      if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(text);return toast('Copied to clipboard');}catch{}}
      const el=document.createElement('textarea');el.value=text;el.style.cssText='position:fixed;left:0;top:0;opacity:0;';
      (root.querySelector('dialog[open] .dialog-body')||root).append(el);el.focus();el.select();const ok=document.execCommand('copy');el.remove();
      if(!ok)throw new Error('Select the text and copy it manually.');toast('Copied to clipboard');
    }
    function renderProjects(failure){
      const focused=root.activeElement?.dataset.project;$('projects').replaceChildren();
      $('project-total').textContent=projects.length+' '+(projects.length===1?'project':'projects');
      for(const [i,p] of projects.entries()){
        const health=failure||p.health||{state:'checking',label:'Checking',detail:'Waiting for a project health check.'};
        const b=node('button',undefined,$('projects'),'project-entry');b.type='button';b.dataset.project=p.id;b.dataset.state=health.state;b.disabled=!!failure||health.state==='unavailable';
        b.style.setProperty('--span',projects.length%2&&i===projects.length-1?12:(Math.floor(i/2)%2?(i%2?7:5):(i%2?5:7)));
        const top=node('div',undefined,b,'project-card-top');const mark=node('span',undefined,top,'project-mark');mark.append(icon('team'));
        const status=node('span',health.label,top,'project-health');status.prepend(icon(health.state==='running'?'check':health.state==='unavailable'?'blocker':'archive'));
        node('h3',p.name,b);node('p',p.goals||'Selected chats, discoveries, and decisions. One memory for this project.',b,'project-description');
        const counts=node('div',undefined,b,'project-card-counts');
        if(p.counts){for(const [key,symbol,label] of [['conversations','message','conversations'],['updates','discovery','updates'],['people','team','people']]){const n=p.counts[key];const text=n+' '+(n===1?{conversations:'conversation',updates:'update',people:'person'}[key]:label);const span=node('span',text,counts);span.prepend(icon(symbol));}}
        node('p',health.detail,b,'project-status-detail');
        const foot=node('div',undefined,b,'project-card-foot');node('span',p.changed?'Active '+relative(p.changed):'Created '+new Date(p.created*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'}),foot,'project-date');const open=node('span',b.disabled?(failure?'Check host':'Storage unavailable'):'Open project',foot,'project-open');open.append(icon(b.disabled?'blocker':'arrow'));
        b.onclick=()=>action(()=>selectProject(p.id));
      }
      if(!projects.length)empty($('projects'),'A shared home for your project','Create a project, or join one using a code from your host.');
      if(focused)root.querySelector('[data-project="'+focused+'"]')?.focus({preventScroll:true});
    }
    function hostHealth(state,label){const el=$('host-health');el.dataset.state=state;el.replaceChildren();const dot=node('span',undefined,el,'status-dot');dot.setAttribute('aria-hidden','true');el.append(document.createTextNode(label));}
    async function loadProjects({poll=false}={}) {
      if(projectsPending)return;projectsPending=true;$('refresh-projects').disabled=true;
      try {
        const data=await api('/team/projects',undefined,AbortSignal.timeout(6000));const changed=JSON.stringify(projects)!==JSON.stringify(data.projects);
        projects=data.projects;projectsCheckedAt=data.checked_at||Date.now()/1000;canManageProjects=true;
        $('new-project').hidden=false;$('all-projects').hidden=false;$('open-restore').hidden=false;
        hostHealth('running','Team Baton host reachable');$('project-check-time').textContent='Checked '+relative(projectsCheckedAt);
        $('project-check-time').title=new Date(projectsCheckedAt*1000).toLocaleString();
        if(changed||!poll||root.querySelector('.project-entry[data-host-failed]'))renderProjects();
        if(!poll)notify('');
      }catch(e){
        if(e.status===403&&!canManageProjects){projects=[];$('new-project').hidden=true;$('all-projects').hidden=true;$('open-restore').hidden=true;renderProjects();hostHealth('checking','Join a project to access shared memory');}
        else{
          const paused=e.status===403||e.status===404;
          const health={state:paused?'attention':'unavailable',label:paused?'Check access':e.status?'Host error':'Host unreachable',detail:paused?e.message:'Could not refresh project health. Showing the last available project details.'};
          hostHealth(health.state,paused?e.message:health.label);$('project-check-time').textContent=projectsCheckedAt?'Last successful check '+relative(projectsCheckedAt):'No successful check yet';
          renderProjects(health);all('.project-entry').forEach(card=>card.dataset.hostFailed='true');$('entry').hidden=false;
          if(!poll)notify(e.message,true);
        }
      }finally{projectsPending=false;$('refresh-projects').disabled=false;}
    }
    async function loadNearby() {
      if(nearbyPending)return;
      nearbyPending=true;$('nearby').setAttribute('aria-busy','true');
      $('nearby-status').textContent='Looking for Team Baton hosts on this server’s local network…';
      $('nearby-hosts').replaceChildren();$('nearby-setup').textContent='';
      try {
        const data=await api('/team/discovery',undefined,AbortSignal.timeout(6000));
        $('nearby-status').textContent=data.state==='disabled'?'LAN discovery is off on this host.':data.state==='unavailable'?'Could not search this network. Try again.':data.hosts.length?data.hosts.length+' nearby '+(data.hosts.length===1?'host.':'hosts.'):'No nearby hosts found. Try again on the same network.';
        for(const [index,server] of data.hosts.entries()){
          let url;try{url=new URL(server.url);}catch{}
          const li=node('li',undefined,$('nearby-hosts'),'nearby-host');li.style.setProperty('--reveal-delay',Math.min(index*28,112)+'ms');li.append(icon('devices'));const text=node('div',undefined,li,'grow');node('h3',server.name,text);node('p',url?.protocol==='https:'?url.origin:server.address,text);
          if(url?.protocol==='https:'&&!url.username&&!url.password&&url.origin!==location.origin){const link=node('a','Open host',li,'btn small');link.href=url.origin+'/team.html?join=1';link.referrerPolicy='no-referrer';link.setAttribute('aria-label','Open '+server.name+' and join');link.append(icon('out'));}
          else badge(url?.origin===location.origin?'This host':'HTTPS needed',li);
        }
        $('nearby-setup').textContent={needs_https:'HTTPS is needed for remote joining.',local_only:'This host is local only.',unavailable:'Discovery port 45837 is unavailable.'}[data.advertising]||'';
      }catch(e){$('nearby-status').textContent=e.status===404?'Team Baton discovery is unavailable here. Ask the host to enable Team Baton and restart it.':e.status===403?e.message:'Could not reach the discovery service. Check the connection and try again.';}
      finally{nearbyPending=false;$('nearby').removeAttribute('aria-busy');}
    }
    async function selectProject(id) {
      if(!/^[a-f0-9]{32}$/.test(id))throw new Error('Choose a valid project.');
      if(pid!==id){for(const name of ['publish','goals-form','processing','device']){$(name).reset();delete $(name).dataset.dirty;}$('secret').value='';$('token-box').hidden=true;$('search').value='';$('search-results').hidden=true;}
      pid=id;contextData=undefined;contextPid=undefined;showAllUpdates=false;draftId=undefined;
      $('brief-preview').textContent='Building your shared briefing…';$('context').textContent='';$('loading').hidden=false;
      $('project').hidden=true;$('entry').hidden=true;notify('');
      if(options.embedded)options.onProject?.(id);else{const url=new URL(location.href);url.searchParams.set('project',id);history.replaceState(null,'',url);}
      setTab('overview');await refresh();await loadContext();
    }
    function renderClients() {
      $('clients').replaceChildren();const active=view.clients.filter(c=>!c.revoked);
      $('client-count').textContent=active.length+' '+(active.length===1?'client':'clients');
      for(const c of view.clients){const li=node('li',undefined,$('clients'),'client-row');const mark=node('span',undefined,li,'client-logo');logo(c.name+' '+c.kind,mark);const text=node('div',undefined,li,'grow');node('div',c.name,text,'client-name');node('p',whoName(c.member)+' · '+(c.kind==='browser'?'Project browser':'Project device'),text,'client-sub');const contact=node('div',undefined,li,'client-contact');
        badge(c.revoked?'Revoked':c.last_used?'Seen '+relative(c.last_used):'Not connected yet',contact,c.revoked?'danger':c.last_used&&Date.now()/1000-c.last_used<600?'ok':'warn');
        if(c.last_used)contact.title=new Date(c.last_used*1000).toLocaleString();}
      if(!view.clients.length)empty($('clients'),'Bring your first AI into the project','Connect a client, then choose the conversations you want to share.',{label:'Connect AI',fn:openConnect});
      const members=view.members.filter(m=>!m.revoked&&!m.id.startsWith('host:'));
      $('member-avatars').replaceChildren();for(const name of ['Host',...members.map(m=>m.name)].slice(0,4))node('span',name.slice(0,1).toUpperCase(),$('member-avatars'),'avatar');
      $('sharing-caption').textContent=(members.length+1)+' '+(members.length?'people':'person')+' with project access';
    }
    function renderUpdates() {
      const superseded=new Set(view.knowledge.map(k=>k.replaces).filter(Boolean));
      const current=view.knowledge.filter(k=>!superseded.has(k.id));$('updates').replaceChildren();
      for(const item of current.slice(0,showAllUpdates?200:5)){
        const row=node('article',undefined,$('updates'),'update-row');const mark=node('span',undefined,row,'kind-mark '+item.kind);mark.append(icon(item.kind==='decision'?'check':item.kind));
        const body=node('div',undefined,row,'grow');const meta=node('div',undefined,body,'update-meta');node('b',LABELS[item.kind]||item.kind,meta);node('span',whoName(item.member),meta);const date=node('time',relative(item.timestamp),meta);date.dateTime=new Date(item.timestamp*1000).toISOString();date.title=new Date(item.timestamp*1000).toLocaleString();
        if(item.origin==='unverified AI')badge('Unverified AI',meta);node('p',item.content,body);
        const tools=node('div',undefined,body,'update-tools');const refs=JSON.parse(item.sources);if(refs.length)button(refs.length+' '+(refs.length===1?'source':'sources'),tools,()=>inspectSources(refs),'', '');
        if(view.host||item.member!=='ai'&&names()[item.member])button('Correct',tools,()=>{openPublish();$('publish').elements.kind.value='correction';$('publish').elements.replaces.value=item.id;},'');
      }
      if(!current.length)empty($('updates'),'Your team is just getting started','Share a discovery or report what changed. Connected does not mean completed.');
      if(current.length>5&&!showAllUpdates)button('Show all '+current.length+' updates',$('updates'),()=>{showAllUpdates=true;renderUpdates();});
      $('history').hidden=!superseded.size;$('history-list').replaceChildren();
      for(const item of view.knowledge.filter(k=>superseded.has(k.id))){const row=node('div',undefined,$('history-list'),'history-row');node('small',(LABELS[item.kind]||item.kind)+' · '+whoName(item.member)+' · replaced',row);node('p',item.content,row);}
      const replace=$('publish').elements.replaces;const prior=replace.value;replace.replaceChildren(new Option('Keep as a new update',''));for(const item of current)replace.add(new Option((LABELS[item.kind]||item.kind)+': '+item.content.slice(0,80),item.id));if([...replace.options].some(o=>o.value===prior))replace.value=prior;
      return current;
    }
    function renderConversations() {
      for(const [parent,limit] of [[$('conversations'),200],[$('recent-conversations'),3]]){
        parent.replaceChildren();
        for(const c of view.conversations.slice(0,limit)){
          const li=node('li',undefined,parent,'list-row');const mark=node('span',undefined,li,'client-logo');logo(c.ai,mark);
          const text=node('div',undefined,li,'grow');const b=node('button',c.title||'Untitled conversation',text,'conversation-title');
          b.onclick=()=>action(async()=>{showDialog('sources-dialog');$('sources-title').textContent=c.title||'Shared conversation';$('sources').textContent='Loading shared messages…';renderMessages((await projectAPI('search?session='+encodeURIComponent(c.id))).messages,$('sources'));});
          node('p',(c.ai||'AI client')+(c.model?' · '+c.model:'')+' · updated '+relative(c.changed),text);
          button('View messages',li,()=>b.click(),'btn quiet small','arrow');
        }
        if(!view.conversations.length)empty(parent,'Your next conversation starts here','Choose this project in a connected client. Its selected messages will appear here.',{label:'Connect AI',fn:openConnect});
      }
    }
    function renderHome(updates){
      const members=view.members.filter(m=>!m.revoked&&!m.id.startsWith('host:'));
      const blockers=updates.filter(item=>item.kind==='blocker').length;
      $('update-summary').textContent=updates.length+' '+(updates.length===1?'update':'updates')+(blockers?' · '+blockers+' '+(blockers===1?'blocker':'blockers'):'');
      $('brief-coverage').textContent=view.conversations.length+' shared '+(view.conversations.length===1?'conversation':'conversations')+' · '+updates.length+' current '+(updates.length===1?'update':'updates');
      $('overview-role').textContent=view.host?'Project host':'Teammate';
      $('overview-created').textContent=new Date(view.created*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
      $('overview-names').textContent=['Host',...members.map(m=>m.name)].join(', ');
      $('overview-sources').replaceChildren();$('overview-sources').className='source-names';
      for(const source of [...new Set(view.conversations.map(c=>c.ai).filter(Boolean))]){const span=node('span',undefined,$('overview-sources'),'source-name');logo(source,span);span.append(document.createTextNode(source));}
      if(!$('overview-sources').childNodes.length)$('overview-sources').textContent='No shared conversations yet';
      const pending=(view.pending||[]).length;$('overview-approval').hidden=!pending||view.archived;
      $('overview-approval').textContent=pending+' '+(pending===1?'join request needs':'join requests need')+' your approval. Review requests';
      const steps=[
        {title:'Connect your first client',description:'Give a coding agent or browser its own project access.',done:view.clients.some(c=>!c.revoked&&c.last_used),label:'Connect AI',run:openConnect},
        {title:'Share a conversation',description:'Select this project in your client. Other chats stay private.',done:view.conversations.length>0,label:'Connection instructions',run:openConnect},
        ...(view.host?[{title:'Bring a teammate in',description:'Send a six-character invite, then approve their request.',done:members.length>0,label:'Invite teammate',run:newInvite}]:[])
      ];
      $('first-steps').hidden=view.archived||steps.every(step=>step.done);$('setup-steps').replaceChildren();
      const nextStep=steps.findIndex(step=>!step.done);
      steps.forEach((step,i)=>{const li=node('li',undefined,$('setup-steps'),'setup-step');const state=node('span',step.done?'':String(i+1),li,'step-state'+(step.done?' done':''));state.setAttribute('aria-label',step.done?'Complete':'Step '+(i+1));if(step.done)state.append(icon('check'));const text=node('div',undefined,li);node('h3',step.title,text);node('p',step.done?['Client has contacted the project.','Shared messages are available.','Your teammate has project access.'][i]:step.description,text);if(!step.done&&i===nextStep)button(step.label,text,step.run,'btn small');});
    }
    function renderMembers() {
      const members=view.members.filter(m=>!m.id.startsWith('host:'));$('members').replaceChildren();
      const hostRow=node('li',undefined,$('members'),'list-row');node('span','H',hostRow,'avatar large');const hostText=node('div',undefined,hostRow,'grow');node('h3','Project host',hostText);node('p','Manages access and agreed decisions',hostText);badge('Host',hostRow);
      for(const member of members){const li=node('li',undefined,$('members'),'list-row');node('span',member.name.slice(0,1).toUpperCase(),li,'avatar large');const body=node('div',undefined,li,'grow');node('h3',member.name,body);node('p',member.revoked?'Access revoked':'Project-only access',body);if(member.revoked)badge('Revoked',li,'danger');else if(view.host)button('Revoke access',li,()=>confirmAction('Revoke '+member.name+'?', 'Their project browser and every device will lose access. Shared history stays in the project.', 'Revoke access',async()=>{await projectAPI('revoke',{member:member.id});await refresh();}),'btn quiet small');}
      $('pending').replaceChildren();$('pending').hidden=!(view.pending||[]).length;
      if(view.pending?.length){node('h3','Waiting for your approval', $('pending'));for(const r of view.pending){const li=node('div',undefined,$('pending'),'list-row');const text=node('div',undefined,li,'grow');node('h3',r.name,text);node('p',r.kind==='browser'?'Project browser':'Project device',text);button('Decline',li,async()=>{await projectAPI('approve',{request:r.id,allow:false});await refresh();});button('Approve',li,async()=>{await projectAPI('approve',{request:r.id,allow:true});await refresh();},'btn primary small');}}
    }
    async function refresh() {
      const currentPid=pid;const next=await projectAPI('view');if(currentPid!==pid)return;
      view=next;$('loading').hidden=true;$('project').hidden=false;$('entry').hidden=true;notify('');
      $('project-name').textContent=view.name;$('goals').textContent=view.goals||'Selected chats, shared context. One project memory for your team.';
      $('project-state').replaceChildren(icon('lock'),document.createTextNode(view.archived?'Archived · readable':'Sharing with this project'));
      $('archive-note').hidden=!view.archived;
      const people=view.members.filter(m=>!m.revoked&&!m.id.startsWith('host:')).length+1;
      $('member-summary').textContent=people+' '+(people===1?'person':'people');$('chat-summary').textContent=view.conversations.length+' '+(view.conversations.length===1?'conversation':'conversations');
      $('people-count').textContent=people;$('conversation-count').textContent=view.conversations.length;
      const last=Math.max(0,...view.conversations.map(c=>c.changed),...view.knowledge.map(k=>k.timestamp));$('last-update').textContent=last?'Updated '+relative(last):'Ready for your first update';
      const picker=$('project-switcher');picker.replaceChildren();const list=projects.some(p=>p.id===pid)?projects:[{id:pid,name:view.name},...projects];for(const p of list){const option=new Option(p.name,p.id);option.disabled=p.health?.state==='unavailable';picker.add(option);}picker.value=pid;
      $('host-controls').hidden=!view.host;$('invite').hidden=!view.host;$('people-invite').hidden=!view.host;
      $('goals-form').hidden=!view.host;if(!$('goals-form').dataset.dirty)$('goals-form').elements.goals.value=view.goals;
      $('publish').elements.kind.querySelector('[value=decision]').disabled=!view.host;
      renderClients();const currentUpdates=renderUpdates();renderConversations();renderMembers();renderHome(currentUpdates);
      if(!$('processing').dataset.dirty){$('models').replaceChildren();for(const pair of view.models){const option=new Option(pair.join(' · '),JSON.stringify(pair));option.dataset.provider=pair[0];$('models').add(option);}
      const selected=JSON.stringify([view.settings.provider,view.settings.model]);if([...$('models').options].some(o=>o.value===selected))$('models').value=selected;
      $('processing').elements.external.checked=view.settings.external;$('processing').elements.budget.value=view.settings.budget;}
      $('usage').textContent='Estimated project use this month: $'+view.usage_estimate.toFixed(4);$('jobs').replaceChildren();for(const job of view.jobs){const li=node('li',undefined,$('jobs'),'list-row');node('span',job.status,li,'badge');node('span',job.error||'Conversation summary',li,'muted');}
      $('processing-state').replaceChildren(view.settings.external?(MindbatonControls.logo(view.settings.provider)||icon('plug')):icon('lock'),document.createTextNode(view.settings.external?'External AI: '+view.settings.provider:'External AI processing is off'));
      $('project-meta').textContent='Project '+pid+' · revision '+view.revision;
      const outdated=contextPid===pid&&contextData?.project_revision<view.revision;$('context-state').textContent=outdated?'Context outdated · refresh before use':contextData?'Updated '+relative(contextData.captured_at):'Shared project briefing';
      for(const form of ['publish','goals-form','device','processing'])for(const field of $(form).elements)field.disabled=view.archived || (form==='publish'&&field.tagName==='OPTION'&&field.value==='decision'&&!view.host);
      for(const id of ['connect-open','publish-open','invite','people-invite','archive'])$(id).disabled=view.archived;
      if(!view.host)$('publish').elements.kind.querySelector('[value=decision]').disabled=true;
      updateSetup();
    }
    async function loadContext() {
      const id=pid;const data=await projectAPI('context');if(id!==pid)return;
      contextData=data;contextPid=id;$('context').textContent=data.text;$('context-state').textContent='Updated '+relative(data.captured_at);
      const lines=data.text.split('\n').filter(line=>line.trim()&&!line.startsWith('[team-baton]')&&!line.startsWith('[/team-baton]'));
      const evidence=lines.filter(line=>/^\[.+\] /.test(line)).map(line=>line.replace(/^\[.*?\]\s*/,''));
      $('brief-preview').textContent=evidence.slice(0,3).map(line=>line.replace(/^(?:\w+ \([^)]+\)|assistant|user):\s*/, '')).join('\n\n')||view.goals||'Share a conversation or an update to build the first project briefing.';
      return data;
    }
    function renderMessages(messages,parent) {
      parent.replaceChildren();for(const m of messages){const row=node('article',undefined,parent,'source-message');const meta=node('div',undefined,row,'update-meta');node('b',m.speaker==='user'?'User':'Assistant',meta);node('span',relative(m.timestamp),meta);const ref=m.source||m.session+'/'+m.id+'@'+m.version;button('Copy source reference',meta,()=>copy(ref));node('p',m.content,row);}
      if(!messages.length)node('p','No matching shared messages. Try another phrase.',parent,'muted');
    }
    async function inspectSources(refs) {showDialog('sources-dialog');$('sources-title').textContent='Supporting messages';const data=await projectAPI('search?source='+encodeURIComponent(refs[0]));renderMessages(data.messages,$('sources'));for(const ref of refs.slice(1)){const next=await projectAPI('search?source='+encodeURIComponent(ref));const fragment=document.createElement('div');renderMessages(next.messages,fragment);$('sources').append(...fragment.childNodes);}}
    function openConnect() {showDialog('connect-dialog');updateSetup();}
    function updateSetup() {
      if(!pid)return;
      const config='project-device.json';const prefix='python3 team_client.py --config '+config;
      const hostURL=location.origin;
      const base=prefix+' init --host '+hostURL+' --project '+pid;
      const names={codex:'Codex',claude:'Claude Code',browser:'Browser extension',mcp:'MCP client'};
      $('setup-title').textContent='Set up '+names[selectedClient];
      if(selectedClient==='codex'||selectedClient==='claude'){
        const hooks=selectedClient==='codex'?'~/.codex/hooks.json':'~/.claude/settings.json';
        $('setup-help').textContent='Create a token, then enter it when the helper asks. Review the hooks in your coding client.';
        $('setup').textContent=base+'\n'+prefix+' install-hooks '+selectedClient+' '+hooks+'\n'+prefix+' bind '+selectedClient+' <session-id>\n'+prefix+' watch';
        $('setup-note').textContent='Bind each session explicitly. Keep watch running for uploads to retry during outages. If the host uses encrypted private-network HTTP, add --private-network to init.';
      }else if(selectedClient==='browser'){
        $('setup-help').textContent='Open the extension, expand Connect a project, and enter the values below.';
        $('setup').textContent='Host: '+hostURL+'\nProject: '+pid+'\nDevice token: paste the token above';
        $('setup-note').textContent='Choose this project under Share this conversation. Every other conversation stays Private. For Tailscale over HTTP, select the encrypted private network option.';
      }else{
        $('setup-help').textContent='Add this project MCP endpoint to your client and use your new token as the bearer credential.';
        $('setup').textContent=hostURL+'/team/'+pid+'/mcp\nAuthorization: Bearer <project-device-token>';
        $('setup-note').textContent='Includes context, search, publish, and handoff tools. Automatic capture requires a supported adapter.';
      }
    }
    async function newInvite() {if(view.archived)throw new Error('Archived projects cannot create invitations.');showDialog('invite-dialog');inviteCode='';delete $('invite-code').dataset.code;$('invite-code').textContent='Creating invite…';$('copy-invite').disabled=true;const d=await projectAPI('invite',{});inviteCode=d.code;$('invite-code').replaceChildren();$('invite-code').dataset.code=d.code;$('invite-code').setAttribute('aria-label','Invite code '+d.code);for(const [i,c] of [...d.code].entries()){const cell=node('span',c,$('invite-code'),c==='-'?'code-separator':'invite-character');cell.setAttribute('aria-hidden','true');cell.style.setProperty('--delay',(i*24)+'ms');}$('invite-expiry').textContent='Expires in ten minutes';$('copy-invite').disabled=false;}
    function openPublish() {if(view.archived)return;showDialog('publish-dialog');}
    function confirmAction(title,description,label,fn) {$('confirm-title').textContent=title;$('confirm-description').textContent=description;$('confirm-action').textContent=label;$('confirm-action').onclick=()=>action(async()=>{await fn();$('confirm-dialog').close();toast('Project access updated');});showDialog('confirm-dialog');}
    function startPoll(enrollment) {clearTimeout(pollTimer);pollTimer=setTimeout(async()=>{try{const r=await api('/team/poll',{poll:enrollment.poll});if(r.status==='pending')return startPoll(enrollment);if(r.status==='approved'){sessionStorage.removeItem('teamEnrollment');$('join-dialog').close();await selectProject(r.project);toast('You now have project access');}else{$('join-status').textContent='Request '+r.status+'. Ask the host for a new invitation.';sessionStorage.removeItem('teamEnrollment');$('join').querySelector('button').disabled=false;}}catch(e){$('join-status').textContent='Waiting for the host to reconnect…';startPoll(enrollment);}},2000);}
    root.addEventListener('keydown',event=>{
      if(event.composedPath().some(el=>el.tagName==='DIALOG'||el.matches?.('input,textarea,select')))event.stopPropagation();
    });
    for(const name of ['goals-form','processing'])$(name).addEventListener('input',()=>$(name).dataset.dirty='true');
    decorate(root);
    all('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
    all('dialog').forEach(dialog=>dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const b=dialog.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)dialog.close();}));
    all('[data-tab]').forEach(b=>{b.onclick=()=>setTab(b.dataset.tab);b.onkeydown=e=>{const tabs=all('[data-tab]');let index=tabs.indexOf(b);if(e.key==='ArrowRight')index=(index+1)%tabs.length;else if(e.key==='ArrowLeft')index=(index+tabs.length-1)%tabs.length;else if(e.key==='Home')index=0;else if(e.key==='End')index=tabs.length-1;else return;e.preventDefault();setTab(tabs[index].dataset.tab,true);};});
    $('refresh-projects').onclick=()=>action(()=>loadProjects());
    $('find-servers').onclick=()=>{const show=$('nearby-results').hidden;$('nearby-results').hidden=!show;$('find-servers').setAttribute('aria-expanded',String(show));if(show)loadNearby();};
    $('all-projects').onclick=()=>action(async()=>{await loadProjects();$('project').hidden=true;$('entry').hidden=false;});
    $('project-switcher').onchange=e=>action(()=>selectProject(e.target.value));
    $('member-summary').onclick=$('manage-people').onclick=$('overview-approval').onclick=()=>setTab('people');$('chat-summary').onclick=$('all-conversations').onclick=()=>setTab('conversations');$('update-summary').onclick=()=>{setTab('overview');root.querySelector('.activity').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});};
    $('connect-open').onclick=()=>action(openConnect);$('invite').onclick=$('people-invite').onclick=()=>action(newInvite);$('rotate-invite').onclick=()=>action(newInvite);
    $('disable-invite').onclick=()=>action(async()=>{await projectAPI('invite',{enabled:false});inviteCode='';delete $('invite-code').dataset.code;$('invite-code').textContent='Invitations disabled';$('invite-expiry').textContent='Create a new code to invite someone';$('copy-invite').disabled=true;});
    $('copy-invite').onclick=()=>action(()=>copy('Join '+view.name+' in Team Baton\n'+location.origin+'/team.html?join=1\nInvite code: '+inviteCode+'\nExpires in ten minutes. Your host will approve access.'));
    $('publish-open').onclick=openPublish;
    $('briefing').onclick=()=>action(async()=>{showDialog('context-dialog');await loadContext();});$('refresh-context').onclick=()=>action(loadContext);
    $('copy-context').onclick=$('copy-full-context').onclick=()=>action(async()=>{const d=await loadContext();if(d)await copy(d.text);});
    $('new-project').onclick=()=>showDialog('create-dialog');$('open-join').onclick=()=>showDialog('join-dialog');$('open-restore').onclick=()=>showDialog('restore-dialog');
    all('[data-client]').forEach(b=>b.onclick=()=>{selectedClient=b.dataset.client;all('[data-client]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));$('device').elements.name.value='My '+({codex:'Codex laptop',claude:'Claude Code laptop',browser:'browser',mcp:'MCP client'}[selectedClient]);updateSetup();});
    $('device').onsubmit=e=>{e.preventDefault();const submit=e.submitter;action(async()=>{submit.disabled=true;try{const d=await projectAPI('devices',{name:$('device').elements.name.value});$('secret').value=d.token;$('secret').type='password';$('token-box').hidden=false;$('setup-details').open=true;await refresh();toast('Project device created');}finally{submit.disabled=!!view.archived;}});};
    $('copy-token').onclick=()=>action(()=>copy($('secret').value));$('reveal-token').onclick=()=>{const hidden=$('secret').type==='password';$('secret').type=hidden?'text':'password';$('reveal-token').textContent=hidden?'Hide':'Show';};
    $('create').onsubmit=e=>{e.preventDefault();action(async()=>{const p=await api('/team/projects',{name:$('create').elements.name.value});$('create-dialog').close();await loadProjects();await selectProject(p.id);});};
    const codeBoxes=all('.code-character');
    const syncCode=()=>{$('join').elements.code.value=codeBoxes.map(box=>box.value).join('');};
    codeBoxes.forEach((box,index)=>{
      box.addEventListener('focus',()=>box.select());
      box.addEventListener('beforeinput',e=>{if(e.data&&!e.isComposing&&/[^a-z0-9]/i.test(e.data))e.preventDefault();});
      box.addEventListener('input',()=>{box.value=box.value.replace(/[^a-z0-9]/gi,'').toUpperCase().slice(-1);syncCode();if(box.value)codeBoxes[index+1]?.focus();});
      box.addEventListener('keydown',e=>{
        if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();codeBoxes[index+(e.key==='ArrowLeft'?-1:1)]?.focus();}
        else if(e.key==='Backspace'&&!box.value&&index>0){e.preventDefault();codeBoxes[index-1].value='';codeBoxes[index-1].focus();syncCode();}
      });
      box.addEventListener('paste',e=>{
        e.preventDefault();const value=e.clipboardData.getData('text').trim();
        if(!/^(?:[a-z0-9]{1,6}|[a-z0-9]{3}-[a-z0-9]{3})$/i.test(value))return;
        const chars=value.replace('-','').toUpperCase();const start=chars.length===6?0:index;
        for(let i=start;i<Math.min(6,start+chars.length);i++)codeBoxes[i].value=chars[i-start];
        syncCode();codeBoxes[Math.min(5,start+chars.length)]?.focus();
      });
    });
    $('join').onsubmit=e=>{e.preventDefault();action(async()=>{const f=$('join').elements;const d=await api('/team/join',{name:f.name.value,code:f.code.value,kind:'browser'});sessionStorage.setItem('teamEnrollment',JSON.stringify(d));$('join-status').textContent='Waiting for host approval. External AI processing '+(d.external_processing?'is enabled.':'is off.');$('join').querySelector('button').disabled=true;startPoll(d);});};
    $('publish').onsubmit=e=>{e.preventDefault();action(async()=>{const f=$('publish').elements;draftId ||= uid();const submit=$('publish').querySelector('button[type=submit],button:not([type])');submit.disabled=true;try{await projectAPI('publish',{id:draftId,kind:f.kind.value,content:f.content.value,replaces:f.replaces.value||null,sources:f.sources.value.split('\n').map(x=>x.trim()).filter(Boolean)});draftId=undefined;$('publish').reset();$('publish-dialog').close();await refresh();await loadContext();toast('Update shared with the project');}finally{submit.disabled=!!view.archived;}});};
    $('goals-form').onsubmit=e=>{e.preventDefault();action(async()=>{await projectAPI('settings',{goals:$('goals-form').elements.goals.value});delete $('goals-form').dataset.dirty;await refresh();toast('Project goal saved');});};
    $('processing').onsubmit=e=>{e.preventDefault();action(async()=>{const f=$('processing').elements;const [provider,model]=JSON.parse(f.model.value);await projectAPI('settings',{settings:{external:f.external.checked,provider,model,budget:Number(f.budget.value)}});delete $('processing').dataset.dirty;await refresh();toast('Processing settings saved');});};
    $('search-form').onsubmit=e=>{e.preventDefault();action(async()=>{const d=await projectAPI('search?q='+encodeURIComponent($('search').value));$('search-results').hidden=false;renderMessages(d.messages,$('search-results'));});};
    $('archive').onclick=()=>confirmAction('Archive this project?','Existing memory stays readable. New shared messages, invitations and updates will stop. This cannot be undone here.','Archive project',async()=>{await projectAPI('settings',{archived:true});await refresh();});
    $('backup').onclick=()=>action(async()=>{await projectAPI('backup',{});toast('Project backed up on the host');});
    $('export').onclick=()=>action(async()=>{const data=await projectAPI('export');const url=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='team-baton-'+pid+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
    $('restore').onchange=e=>action(async()=>{if(!e.target.files.length)return;const data=JSON.parse(await e.target.files[0].text());const p=await api('/team/projects',{backup:data});$('restore-dialog').close();await loadProjects();await selectProject(p.id);});
    const controller={selectProject,copyBriefing:()=>view&&$('entry').hidden?$('copy-context').click():toast('Choose a project first'),search:()=>{if(!view||!$('entry').hidden)return;setTab('conversations');$('search').focus();},root};host.teamBaton=controller;
    action(async()=>{await loadProjects();if(!options.embedded&&canManageProjects&&!new URLSearchParams(location.search).has('join')&&!sessionStorage.getItem('teamEnrollment')){location.replace('/#team'+(/^[a-f0-9]{32}$/.test(pid)?'/'+pid:''));return;}$('loading').hidden=true;if(pid&&/^[a-f0-9]{32}$/.test(pid))await selectProject(pid);else if(projects.length===1&&!new URLSearchParams(location.search).has('join'))await selectProject(projects[0].id);else{$('entry').hidden=false;if(!canManageProjects||new URLSearchParams(location.search).has('join'))showDialog('join-dialog');}const pending=sessionStorage.getItem('teamEnrollment');if(pending){showDialog('join-dialog');$('join-status').textContent='Waiting for host approval.';startPoll(JSON.parse(pending));}});
    const timer=setInterval(()=>{if(!host.isConnected){clearInterval(timer);clearTimeout(pollTimer);return;}if(document.hidden||host.closest('[hidden]'))return;if(!$('entry').hidden&&canManageProjects){action(()=>loadProjects({poll:true}));return;}if(view&&$('entry').hidden&&!root.querySelector('dialog[open],.mb-menu:popover-open')&&!root.activeElement?.matches('input,textarea,select'))action(refresh);},10000);
    return controller;
  }
  return {open,mount};
})();
