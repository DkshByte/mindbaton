/* One select treatment for the app and its project view; native values still own forms. */
window.MindbatonControls=(()=>{
  const controls=new WeakMap(),roots=new WeakSet();let count=0,active;
  const paths={gemini:'gemini-color',groq:'groq',openai:'openai',claude:'claude-color',anthropic:'anthropic',codex:'codex-color',chatgpt:'openai'};
  function logo(provider){
    const file=paths[String(provider).toLowerCase()];if(!file)return null;
    const el=document.createElement(file.endsWith('-color')?'img':'span');el.className='mb-logo'+(file.endsWith('-color')?' color':'');
    const url='/assets/icons/lh/'+file+'.svg';if(el.tagName==='IMG'){el.src=url;el.alt='';}else el.style.setProperty('--logo','url("'+url+'")');el.setAttribute('aria-hidden','true');return el;
  }
  function provider(option,select){
    if(option?.dataset.provider)return option.dataset.provider;
    if(select.dataset.p)return select.dataset.p;
    return paths[String(option?.value).toLowerCase()]?option.value:'';
  }
  function enhance(select){
    if(controls.has(select)||select.multiple||select.size>1||!HTMLElement.prototype.showPopover)return;
    const label=select.getAttribute('aria-label')||[...(select.labels||[])].map(l=>{const clone=l.cloneNode(true);clone.querySelectorAll('select').forEach(s=>s.remove());return clone.textContent.trim();}).join(' ')||'Choose an option';
    const wrap=document.createElement('span');wrap.className='mb-select';select.before(wrap);wrap.append(select);select.classList.add('mb-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    const trigger=document.createElement('button');trigger.type='button';trigger.className='mb-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
    const menu=document.createElement('div');menu.className='mb-menu';menu.id='mb-select-'+(++count);menu.setAttribute('popover','auto');menu.setAttribute('role','listbox');menu.setAttribute('aria-label',label);trigger.setAttribute('aria-controls',menu.id);wrap.append(trigger,menu);
    let at=select.selectedIndex,buffer='',typedAt=0;
    const disabled=i=>!select.options[i]||select.options[i].disabled||select.options[i].parentElement.disabled;
    const items=()=>[...menu.querySelectorAll('[role=option]')];
    function mark(){items().forEach((item,i)=>item.dataset.active=String(i===at));const item=items()[at];if(item){trigger.setAttribute('aria-activedescendant',item.id);const top=item.offsetTop,bottom=top+item.offsetHeight;if(top<menu.scrollTop)menu.scrollTop=top;else if(bottom>menu.scrollTop+menu.clientHeight)menu.scrollTop=bottom-menu.clientHeight;}}
    function close(){if(menu.matches(':popover-open'))menu.hidePopover();trigger.setAttribute('aria-expanded','false');trigger.removeAttribute('aria-activedescendant');if(active?.menu===menu)active=undefined;}
    function sync(){
      trigger.disabled=select.disabled;trigger.replaceChildren();const option=select.selectedOptions[0];const mark=logo(provider(option,select));if(mark)trigger.append(mark);
      const value=document.createElement('span');value.className='mb-value';value.textContent=option?.textContent||'Choose an option';trigger.append(value);trigger.setAttribute('aria-label',label+': '+value.textContent);
      const arrow=document.createElementNS('http://www.w3.org/2000/svg','svg');arrow.classList.add('mb-chevron');arrow.setAttribute('viewBox','0 0 24 24');arrow.setAttribute('aria-hidden','true');arrow.innerHTML='<use href="/assets/icons/ui/sprite.svg#chevron-down"/>';trigger.append(arrow);
      if(menu.matches(':popover-open'))close();
    }
    function open(){
      if(trigger.disabled)return;active?.close();menu.replaceChildren();let group;
      [...select.options].forEach((option,i)=>{
        const next=option.parentElement.tagName==='OPTGROUP'?option.parentElement.label:'';
        if(next&&next!==group){const heading=document.createElement('div');heading.className='mb-group';heading.textContent=next;menu.append(heading);}group=next;
        const item=document.createElement('div');item.className='mb-option';item.id=menu.id+'-'+i;item.dataset.index=i;item.setAttribute('role','option');item.setAttribute('aria-selected',String(i===select.selectedIndex));item.setAttribute('aria-disabled',String(!!disabled(i)));
        const image=logo(provider(option,select));if(image)item.append(image);const text=document.createElement('span');text.className='mb-option-label';text.textContent=option.textContent;item.append(text);
        if(i===select.selectedIndex){const tick=document.createElementNS('http://www.w3.org/2000/svg','svg');tick.setAttribute('viewBox','0 0 24 24');tick.setAttribute('aria-hidden','true');tick.classList.add('mb-tick');tick.innerHTML='<use href="/assets/icons/ui/sprite.svg#check"/>';item.append(tick);}menu.append(item);
      });
      const r=trigger.getBoundingClientRect(),width=Math.min(Math.max(r.width,240),innerWidth-24);menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(r.left,innerWidth-width-12))+'px';
      const below=innerHeight-r.bottom-12,above=r.top-12,down=below>=Math.min(280,above);menu.style.maxHeight=Math.max(40,Math.min(320,down?below:above))+'px';menu.style.top=down?r.bottom+6+'px':'auto';menu.style.bottom=down?'auto':innerHeight-r.top+6+'px';
      menu.showPopover();trigger.setAttribute('aria-expanded','true');at=select.selectedIndex;if(disabled(at))at=[...select.options].findIndex((_,i)=>!disabled(i));active={menu,close,trigger,rect:trigger.getBoundingClientRect()};mark();
    }
    function choose(){if(disabled(at))return;select.selectedIndex=at;close();sync();select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));}
    trigger.addEventListener('click',e=>{e.preventDefault();menu.matches(':popover-open')?close():open();});
    trigger.addEventListener('keydown',e=>{
      const showing=menu.matches(':popover-open');
      if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
        e.preventDefault();e.stopPropagation();if(!showing)open();const available=[...select.options].map((_,i)=>i).filter(i=>!disabled(i));if(!available.length)return;
        if(e.key==='Home')at=available[0];else if(e.key==='End')at=available.at(-1);else if(showing){const pos=available.indexOf(at);at=available[Math.max(0,Math.min(available.length-1,pos+(e.key==='ArrowDown'?1:-1)))];}mark();
      }else if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();showing?choose():open();}
      else if(e.key==='Escape'&&showing){e.preventDefault();e.stopPropagation();close();}
      else if(e.key==='Tab'&&showing){choose();}
      else if(e.key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();e.stopPropagation();if(!showing)open();const now=performance.now();buffer=now-typedAt>750||buffer===e.key.toLowerCase()?e.key.toLowerCase():buffer+e.key.toLowerCase();typedAt=now;const options=[...select.options];for(let step=1;step<=options.length;step++){const i=(at+step)%options.length;if(!disabled(i)&&options[i].textContent.trim().toLowerCase().startsWith(buffer)){at=i;mark();break;}}}
    });
    menu.addEventListener('pointerdown',e=>e.preventDefault());
    menu.addEventListener('click',e=>{const item=e.target.closest('[role=option]');if(item){at=Number(item.dataset.index);choose();trigger.focus();}});
    menu.addEventListener('toggle',e=>{if(e.newState==='closed')close();});
    select.addEventListener('change',sync);select.form?.addEventListener('reset',()=>queueMicrotask(sync));controls.set(select,{sync});sync();
  }
  function scan(node){if(node.matches?.('select'))enhance(node);node.querySelectorAll?.('select').forEach(enhance);}
  function install(root){
    if(roots.has(root))return;roots.add(root);scan(root);
    new MutationObserver(records=>{const changed=new Set();for(const r of records){const select=r.target.closest?.('select');if(select)changed.add(select);for(const node of r.addedNodes)if(node.nodeType===1)scan(node);}for(const select of changed)controls.get(select)?.sync();}).observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected']});
    root.addEventListener('scroll',e=>{if(active&&!active.menu.contains(e.target))closeIfMoved();},true);
  }
  function closeIfMoved(){if(!active)return;const r=active.trigger.getBoundingClientRect(),before=active.rect;if(r.top!==before.top||r.left!==before.left||r.width!==before.width)active.close();}
  addEventListener('resize',closeIfMoved);
  document.addEventListener('DOMContentLoaded',()=>install(document));
  return {install,logo};
})();
