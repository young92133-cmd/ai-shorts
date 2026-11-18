// Independent browser layout audit of the exported child template. The actual
// render additionally runs HyperFrames --strict; MP4 checks are in Python.
import {createRequire} from 'node:module';
import {readFile, writeFile, mkdir, readdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const project=path.resolve(process.argv[2]);
const report=path.resolve(process.argv[3]);
const require=createRequire(path.join(root,'renderers/hyperframes/package.json'));
const {default:puppeteer}=await import(pathToFileURL(require.resolve('puppeteer-core')).href);
async function findChrome(dir) {
  for (const entry of await readdir(dir,{withFileTypes:true})) {
    const p=path.join(dir,entry.name);
    if(entry.isDirectory()) {const found=await findChrome(p);if(found)return found;}
    else if(entry.name==='chrome-headless-shell.exe')return p;
  }
}
const source=await readFile(path.join(project,'compositions/shorts.html'),'utf8');
const child=source.replace(/^<template>\s*/,'').replace(/\s*<\/template>\s*$/,'');
const html=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><script src="assets/gsap.min.js"></script><style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden}</style></head><body>${child}</body></html>`;
const mime={'.js':'text/javascript','.ttf':'font/ttf','.jpg':'image/jpeg','.png':'image/png','.mp4':'video/mp4'};
const server=createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://127.0.0.1');
    if(url.pathname==='/__layout.html'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
    const target=path.resolve(project,'.'+decodeURIComponent(url.pathname));
    if(!target.startsWith(project+path.sep))throw Error('outside project');
    res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');res.end(await readFile(target));
  } catch {res.statusCode=404;res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await puppeteer.launch({executablePath:await findChrome(path.join(root,'.tools/hyperframes/cache/chrome')),headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-background-networking']});
  const page=await browser.newPage();await page.setViewport({width:1080,height:1920,deviceScaleFactor:1});
  await page.setRequestInterception(true);
  page.on('request',request=>request.url().startsWith('http://127.0.0.1:')?request.continue():request.abort());
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/__layout.html`,{waitUntil:'networkidle0'});
  await page.evaluate(()=>document.fonts.ready);
  const layout=JSON.parse(await readFile(path.join(project,'layout-map.json'),'utf8'));
  const result=await page.evaluate((safe)=>{
    const total=Number(document.querySelector('[data-composition-id="shorts"]').dataset.duration);
    const timeline=window.__timelines.shorts;
    const clocks=[...document.querySelectorAll('[data-start][data-duration]')];
    const text=[...document.querySelectorAll('[data-key-text="true"]')];
    const outside=[],overlaps=[],measurements=new Map();
    function active(el,t){for(let node=el;node;node=node.parentElement){if(node.hasAttribute('data-start')){const a=Number(node.dataset.start),b=a+Number(node.dataset.duration);if(t<a||t>=b)return false;}}return true;}
    for(let frame=0;frame<Math.floor(total*30+.5);frame++) {
      const t=frame/30;timeline.seek(t,false);
      for(const el of clocks)el.style.visibility=active(el,t)?'visible':'hidden';
      const caps=[],titles=[];
      for(const el of text){
        if(!active(el,t)||Number(getComputedStyle(el).opacity)<.02)continue;
        const range=document.createRange();range.selectNodeContents(el);
        const rects=[...range.getClientRects()].filter(r=>r.width>.1&&r.height>.1);
        for(const r of rects)if(r.left<safe.left-1||r.right>1080-safe.right+1||r.top<safe.top-1||r.bottom>1920-safe.bottom+1)outside.push({frame,id:el.id||el.className,bounds:[r.left,r.top,r.right,r.bottom]});
        const rect=el.getBoundingClientRect();
        if(el.classList.contains('caption'))caps.push(rect);
        if(el.classList.contains('native-heading')||el.classList.contains('adaptive-title'))titles.push(rect);
        measurements.set(el.id||el.className,{id:el.id||el.className,fontSize:getComputedStyle(el).fontSize,text:el.textContent,bounds:[rect.left,rect.top,rect.right,rect.bottom]});
      }
      for(const a of caps)for(const b of titles)if(a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top)overlaps.push(frame);
    }
    return {frames:Math.floor(total*30+.5),safe_area:safe,outside_count:outside.length,outside:outside.slice(0,20),caption_title_overlap_frames:[...new Set(overlaps)],text:[...measurements.values()],font_loaded:document.fonts.check('700 52px "Noto Sans KR"')};
  },layout.safe_area);
  result.page_errors=errors;result.note='Independent child-template DOM/GSAP audit at every output frame; actual MP4 and HyperFrames strict checks verified separately.';
  await mkdir(path.dirname(report),{recursive:true});await writeFile(report,JSON.stringify(result,null,2));
  console.log(JSON.stringify({report,frames:result.frames,outside_count:result.outside_count,overlap_frames:result.caption_title_overlap_frames.length,font_loaded:result.font_loaded,page_errors:errors}));
  if(result.outside_count||result.caption_title_overlap_frames.length||!result.font_loaded||errors.length)process.exitCode=1;
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
