import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {randomInt,randomBytes} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),base=path.join(root,'tmp/docking-audit');
const browserMode=process.argv.includes('--browser'),quick=process.argv.includes('--quick'),extended=process.argv.includes('--extended');
const meta=JSON.parse(fs.readFileSync(path.join(base,'assets/assets.json'))),raw=fs.readFileSync(path.join(base,'assets/maps.bin'));
const maps=new Int32Array(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength));
const native=await import('../research/lightweight_docking.mjs');
let browser,page,server,loadMs=0;
if(browserMode){
 const {chromium}=await import(pathToFileURL('C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs'));
 server=http.createServer((req,res)=>{
  const files={'/':'','/kernel.mjs':path.join(root,'research/lightweight_docking.mjs'),'/assets.json':path.join(base,'assets/assets.json'),'/maps.bin':path.join(base,'assets/maps.bin')};
  if(!(req.url in files)){res.writeHead(404);res.end();return;}
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Local docking benchmark</title>');return;}
  res.setHeader('Content-Type',req.url.endsWith('.mjs')?'text/javascript':'application/octet-stream');fs.createReadStream(files[req.url]).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});page=await browser.newPage();
 const t=performance.now();await page.goto(`http://127.0.0.1:${server.address().port}`);
 await page.evaluate(async()=>{globalThis.kernel=await import('/kernel.mjs');globalThis.meta=await(await fetch('/assets.json')).json();globalThis.maps=new Int32Array(await(await fetch('/maps.bin')).arrayBuffer());});loadMs=performance.now()-t;
}else{globalThis.kernel=native;globalThis.meta=meta;globalThis.maps=maps;}
const execute=async(fn,arg)=>browserMode?page.evaluate(fn,arg):fn(arg);
const run=async({jobs,mode,binding})=>{
 const {score,commitJob,bundleCommitment}=globalThis.kernel,meta=globalThis.meta,maps=globalThis.maps;
 const start=performance.now(),states=[];let useful=0,kernelTime=0,hashTime=0,owned=maps.byteLength;
 for(const job of jobs){
  const ref=[];for(let i=0;i<3;i++)ref.push(score(meta,maps,job.id,job.start,job.count,{records:false}).kernel_ms);
  ref.sort((a,b)=>a-b);useful+=ref[1];
  const computed=score(meta,maps,job.id,job.start,job.count,{records:mode!=='B'});kernelTime+=computed.kernel_ms;
  const state=await commitJob(binding,job,computed,mode);hashTime+=state.commit_ms;states.push(state);
  owned+=computed.scores.byteLength+(computed.values?.byteLength||0);
 }
 const t=performance.now(),commitment=await bundleCommitment(binding,states);hashTime+=performance.now()-t;
 globalThis.pending=states;
 return {headers:states.map(s=>s.header),commitment,useful_ms:useful,kernel_ms:kernelTime,commit_ms:hashTime,owned_array_bytes:owned,diagnostic_wall_ms:performance.now()-start};
};
const open=async(indices)=>{
 const t=performance.now(),answers=globalThis.pending.map((state,j)=>globalThis.kernel.openings(state,indices[j]));
 const text=JSON.stringify(answers);return {answers,opening_ms:performance.now()-t,opening_wire_bytes:new TextEncoder().encode(text).length};
};
const actives=meta.ligands.filter(l=>l.label==='active'),decoys=meta.ligands.filter(l=>l.label==='decoy'),ids=[];
for(let i=0;i<8;i++)ids.push(actives[i].id,decoys[i].id);
await execute(({id})=>globalThis.kernel.score(globalThis.meta,globalThis.maps,id,0,256),{id:ids[0]});
const transcript=[],summary=[];
try{
 for(const mode of (quick?['C']:extended?['B','C']:['B','C','E']))for(const jobsCount of (quick?[1]:[1,4,16]))for(const count of (quick?[256]:extended?[16384]:[256,1024,4096])){
  const jobs=ids.slice(0,jobsCount).map(id=>({id,start:8192,count,mode})),repeats=[];
  for(let rep=0;rep<(quick?1:3);rep++){
   const binding=randomBytes(32).toString('hex'),result=await execute(run,{jobs,mode,binding});
   // Trusted harness selects challenges only after the browser returned roots.
   const weights=jobs.map(j=>meta.ligands.find(l=>l.id===j.id).heavy_atoms),total=weights.reduce((a,b)=>a+b,0),draws=[];
   for(let q=0;q<32;q++){let choice=randomInt(total),j=0;while(choice>=weights[j])choice-=weights[j++];draws.push([j,randomInt(count)]);}
   const indices=jobs.map(()=>new Set());for(const [j,i] of draws)indices[j].add(i);
   for(let j=0;j<jobs.length;j++){
    const buffer=Buffer.from(result.headers[j].scores,'base64'),scores=new Int32Array(buffer.buffer.slice(buffer.byteOffset,buffer.byteOffset+buffer.byteLength));
    let best=0;for(let i=1;i<count;i++)if(scores[i]<scores[best])best=i;indices[j].add(best);
    if(mode==='E')for(let k=0;k<count;k+=64){let best=k;for(let i=k+1;i<Math.min(k+64,count);i++)if(scores[i]<scores[best])best=i;indices[j].add(best);}
   }
   const opened=await execute(open,indices.map(x=>[...x]));
   const actual=result.kernel_ms+result.commit_ms+opened.opening_ms;
   repeats.push({useful_ms:result.useful_ms,kernel_ms:result.kernel_ms,commit_ms:result.commit_ms,opening_ms:opened.opening_ms,client_ms:actual,useful_work_fraction:Math.min(result.useful_ms,actual)/actual,owned_array_bytes:result.owned_array_bytes,opening_wire_bytes:opened.opening_wire_bytes,commitment_wire_bytes:Buffer.byteLength(JSON.stringify(result.headers))});
   transcript.push({runtime:browserMode?'chrome':'node',mode,jobsCount,count,rep,binding,jobs,headers:result.headers,root:result.commitment,draws,answers:opened.answers,timings:repeats.at(-1)});
  }
  summary.push({mode,jobs:jobsCount,poses_per_job:count,repeats});console.log(JSON.stringify({mode,jobs:jobsCount,count,client_ms:repeats.map(r=>+r.client_ms.toFixed(2))}));
 }
 const runtime=browserMode?'chrome':'node',tag=runtime+(extended?'-extended':'');fs.writeFileSync(path.join(base,`${tag}-transcripts.json`),JSON.stringify(transcript));
 const result={runtime,version:browserMode?browser.version():process.version,cold_loopback_asset_load_ms:loadMs,map_bytes:maps.byteLength,host_process_memory:process.memoryUsage(),summary};
 if(browserMode){const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');result.chrome_metrics=(await cdp.send('Performance.getMetrics')).metrics;}
 fs.writeFileSync(path.join(root,`docs/evaluation/docking_lightweight_2026-09-07/${tag}_bench.json`),JSON.stringify(result,null,2)+'\n');
}finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));}
