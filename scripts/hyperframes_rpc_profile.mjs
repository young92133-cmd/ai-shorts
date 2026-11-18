// Diagnostic-only Puppeteer public Page instrumentation. Never changes package
// files, quality, animation clocks, arguments or return values. No text/URLs,
// function bodies, credentials or media payloads are written to the profile.
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import {writeFileSync} from 'node:fs';
import {performance} from 'node:perf_hooks';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'renderers/hyperframes/package.json'));
const {Page}=await import(pathToFileURL(require.resolve('puppeteer-core')).href);
const originalEvaluate=Page.prototype.evaluate;
const states=new WeakMap();const calls={};const resources=[];
const workerCycle=[],workerAfterPaint=[];const start=performance.now();
function add(key,duration){(calls[key]??=[]).push(duration);}
function category(source){
  if(source.includes('window.__hf.seek(t, opts)'))return 'seek_rpc';
  if(source.includes('__hfDecodeDynamicCssBackgroundImages'))return 'css_background_ready_rpc';
  if(source.includes('waitForActiveLuts'))return 'lut_ready_rpc';
  if(source.includes('__hf_de_canvas')&&source.includes('fid'))return 'draw_paint_bitmap_kick_rpc';
  if(source.includes('document.fonts'))return 'font_ready_rpc';
  if(source.includes('__hfEncWorker'))return 'image_encoder_worker_setup_rpc';
  if(source.includes('dataUri')&&source.includes('video'))return 'video_injection_rpc';
  return 'other_rpc';
}
Page.prototype.evaluate=async function(fn,...args){
  let state=states.get(this);
  if(!state){
    state={pending:new Map(),resourceSnapshot:false};states.set(this,state);
    const expose=this.exposeFunction;
    this.exposeFunction=function(name,callback){
      if(name==='__hfFrameReady'){
        const original=callback;
        callback=function(id,...values){
          const item=state.pending.get(id),now=performance.now();
          if(item){workerCycle.push(now-item.start);if(item.paintEnd)workerAfterPaint.push(now-item.paintEnd);state.pending.delete(id);}
          return original(id,...values);
        };
      }
      return expose.call(this,name,callback);
    };
  }
  const source=String(fn),key=category(source);let item;
  if(key==='draw_paint_bitmap_kick_rpc'&&Number.isFinite(args[0]?.fid)){
    if(!state.resourceSnapshot){
      state.resourceSnapshot=true;
      const snapshot=await originalEvaluate.call(this,()=>({
        navigation:performance.getEntriesByType('navigation').map(x=>({domInteractive:x.domInteractive,domContentLoaded:x.domContentLoadedEventEnd,load:x.loadEventEnd,responseEnd:x.responseEnd})),
        assets:performance.getEntriesByType('resource').filter(x=>x.name.startsWith('http://127.0.0.1:')).map(x=>({file:new URL(x.name).pathname.split('/').pop(),initiator:x.initiatorType,duration:x.duration,bytes:x.transferSize,start:x.startTime,responseEnd:x.responseEnd})),
        fontLoaded:document.fonts.check('700 52px "Noto Sans KR"')
      }));resources.push(snapshot);
    }
    item={start:performance.now()};state.pending.set(args[0].fid,item);
  }
  const begin=performance.now();
  try{return await originalEvaluate.call(this,fn,...args);}
  finally{const now=performance.now();add(key,now-begin);if(item)item.paintEnd=now;}
};
function stats(values){
  const sorted=[...values].sort((a,b)=>a-b);const n=values.length;
  return {count:n,total_ms:values.reduce((a,b)=>a+b,0),mean_ms:n?values.reduce((a,b)=>a+b,0)/n:null,p50_ms:n?sorted[Math.floor((n-1)*.5)]:null,p95_ms:n?sorted[Math.floor((n-1)*.95)]:null};
}
process.once('exit',()=>{
  const file=process.env.AI_SHORTS_RPC_PROFILE_FILE;if(!file)return;
  try{writeFileSync(file,JSON.stringify({elapsed_ms:performance.now()-start,calls:Object.fromEntries(Object.entries(calls).map(([k,v])=>[k,stats(v)])),worker_capture_to_frame_callback:stats(workerCycle),worker_after_paint_rpc_to_callback:stats(workerAfterPaint),resources,note:'Diagnostic Page RPC wall intervals include transport/waits. Worker intervals include JPEG encode + base64/IPC delivery, not isolated codec CPU. Concurrent intervals must not be added as sequential wall time.'},null,2));}catch{}
});
