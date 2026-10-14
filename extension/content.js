/* Isolated, persistent overlay. No document-wide keyboard interception. */
(() => {
  if (document.getElementById('m13-qc-host')) return;
  const host = document.createElement('div');
  host.id = 'm13-qc-host';
  host.style.cssText = 'position:fixed;inset:0;z-index:2147483000;pointer-events:none';
  const shadow = host.attachShadow({mode:'open'});
  shadow.innerHTML = `<style>
    :host {font:14px system-ui;color:#172738}
    button {pointer-events:auto;cursor:pointer;border:1px solid #ddd;border-radius:10px;background:#211f20;color:white;box-shadow:0 4px 18px #0003}
    #toggle {position:fixed;right:16px;top:110px;width:48px;height:48px;padding:5px}
    img {width:100%;height:100%}
    #board {position:fixed;top:102px;right:12px;bottom:12px;width:min(var(--qc-width,390px),calc(100vw - 64px));pointer-events:auto;border:1px solid #d5dde7;border-radius:12px;background:white;box-shadow:0 6px 26px #0003;overflow:hidden}
    iframe {width:100%;height:100%;border:0;display:block;background:#f6f8fb}
    #resize {position:absolute;left:0;top:0;bottom:0;width:6px;cursor:ew-resize;touch-action:none}
    [hidden] {display:none!important}
    @media(max-height:500px) {#board{top:52px}}
  </style><button id="toggle" title="Mở/đóng QC" aria-label="Mở/đóng QC" aria-expanded="false"><img alt="QC"></button><section id="board" hidden aria-label="Bảng QC"><iframe title="M13 QC 2D"></iframe><div id="resize" title="Kéo để đổi chiều rộng"></div></section>`;
  const toggle=shadow.getElementById('toggle'), board=shadow.getElementById('board');
  const iframe=shadow.querySelector('iframe');
  shadow.querySelector('img').src=chrome.runtime.getURL('logo.svg');
  document.documentElement.append(host);
  let ui={open:false,width:390}, loaded=false, pending=Promise.resolve(), job='';
  const valid=()=>/^\/tasks\/\d+\/jobs\/\d+\/?$/.test(location.pathname);
  const send=message=>chrome.runtime.sendMessage(message).catch(()=>null);
  function render() {
    host.style.display=valid()?'block':'none';
    const opened=valid()&&ui.open;
    board.hidden=!opened; toggle.hidden=opened;
    toggle.setAttribute('aria-expanded',String(opened));
    board.style.setProperty('--qc-width',`${ui.width}px`);
    if(opened&&!loaded) {loaded=true;iframe.src=chrome.runtime.getURL('sidepanel.html?embedded=1');}
    iframe.contentWindow?.postMessage({type:'QC_VISIBILITY',visible:opened},chrome.runtime.getURL('').slice(0,-1));
  }
  function setOpen(open) {
    pending=pending.then(async()=>{
      ui.open=open===undefined?!ui.open:open;
      render();
      if(!ui.open) send({type:'PANEL_FOCUS',focused:false});
      await send({type:'UI_SET',value:ui});
    });
  }
  toggle.onclick=()=>setOpen();
  chrome.runtime.onMessage.addListener((m,_sender,reply)=>{
    if(m.type==='QC_TOGGLE') {if(valid()){setOpen();reply({ok:true});}else reply({ok:false});}
  });
  // Only the extension's actual iframe may request closing or report focus.
  window.addEventListener('message',event=>{
    if(event.source!==iframe.contentWindow||event.origin!==chrome.runtime.getURL('').slice(0,-1)) return;
    if(event.data?.type==='QC_CLOSE') setOpen(false);
    if(event.data?.type==='QC_FOCUS') send({type:'PANEL_FOCUS',focused:Boolean(event.data.focused)&&ui.open&&valid()});
  });
  document.addEventListener('pointerdown',event=>{
    if(!event.composedPath().includes(host)) send({type:'PANEL_FOCUS',focused:false});
  },true);
  const grip=shadow.getElementById('resize');
  grip.onpointerdown=event=>{grip.setPointerCapture(event.pointerId);event.preventDefault();send({type:'PANEL_FOCUS',focused:true});};
  grip.onpointermove=event=>{
    if(!grip.hasPointerCapture(event.pointerId)) return;
    ui.width=Math.max(300,Math.min(650,innerWidth-event.clientX-12));render();
  };
  grip.onpointerup=event=>{grip.releasePointerCapture(event.pointerId);send({type:'UI_SET',value:ui});};
  // URL checks cover history updates, including CVAT's SPA; no DOM polling/mutation loop.
  setInterval(()=>{
    if(job!==location.pathname){job=location.pathname;render();if(!valid())send({type:'PANEL_FOCUS',focused:false});}
  },400);
  send({type:'UI_GET'}).then(result=>{if(result?.ok)ui=result.value;render();});
})();
