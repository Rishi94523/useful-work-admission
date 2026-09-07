import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const cache=path.resolve('tmp/docking-pilot');
const out=path.resolve('docs/evaluation/docking_pilot_2026-09-06');
const plan=JSON.parse(await readFile(path.join(out,'browser_jobs.json'),'utf8'));
const allowed=new Map(['/webina/vina.js','/webina/vina.wasm','/webina/vina.worker.js'].map(x=>[x,path.join(cache,x.slice(1))]));
// Emscripten's pthread fallback refers to this distribution filename.
allowed.set('/webina/vina.1.0.5.js',path.join(cache,'webina/vina.js'));
allowed.set('/worker.mjs',path.resolve('research/docking_browser_worker.mjs'));
for(const s of plan.cases) for(const f of [s.receptor,s.ligand]) allowed.set('/inputs/'+f,path.join(cache,'inputs',f));
const server=createServer(async(req,res)=>{
  res.setHeader('Cross-Origin-Opener-Policy','same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy','require-corp');
  const url=new URL(req.url,'http://localhost').pathname;
  if(url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Local docking experiment</title><p>Local benchmark; no access tokens are issued.</p>');return;}
  if(!allowed.has(url)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',url.endsWith('.wasm')?'application/wasm':url.endsWith('.js')||url.endsWith('.mjs')?'text/javascript':'text/plain');
  try{res.end(await readFile(allowed.get(url)));}catch{res.writeHead(500).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
  const page=await browser.newPage();
  page.on('console',message=>{if(message.type()==='error')console.error(message.text());});
  await page.goto('http://127.0.0.1:'+server.address().port);
  const evidence={scope:'Actual local Chromium Webina 1.0.5 / Vina 1.2.3; fresh worker per call, local loopback assets, one requested CPU. No public deployment, phone, fresh science or access-security claim.',browser:browser.version(),rows:[]};
  const fullSearch=process.argv.includes('--full-search');
  const jobs=fullSearch?[{case:'2P16',exhaustiveness:1,max_evals:0,seed:104729}]:(process.argv.includes('--smoke')?plan.jobs.slice(0,1):plan.jobs);
  const outputName=fullSearch?'browser_full_search.json':process.argv.includes('--smoke')?'browser_smoke.json':'browser_scaling.json';
  for(const job of jobs){
    const s=plan.cases.find(x=>x.id===job.case);
    const row=await page.evaluate(async({job,s})=>{
      const begin=performance.now();
      const [receptor,ligand]=await Promise.all([s.receptor,s.ligand].map(f=>fetch('/inputs/'+f).then(r=>r.text())));
      const fetched=performance.now();
      return await new Promise(resolve=>{
        const worker=new Worker('/worker.mjs',{type:'module'});
        const timer=setTimeout(()=>{worker.terminate();resolve({ok:false,timeout:true});},120000);
        const finish=r=>{clearTimeout(timer);worker.terminate();resolve({...job,...r,fetch_ms:fetched-begin,page_total_ms:performance.now()-begin});};
        worker.onmessage=e=>finish(e.data);
        worker.onerror=e=>finish({ok:false,error:e.message});
        worker.postMessage({...job,receptor,ligand,params:s.params});
      });
    },{job,s});
    const label=`browser_${job.case}_e${job.exhaustiveness}_seed${job.seed}${fullSearch?'_full':''}`;
    if(row.pose){await writeFile(path.join(cache,'runs',label+'.pdbqt'),row.pose);row.pose_path='tmp/docking-pilot/runs/'+label+'.pdbqt';row.pose_bytes=Buffer.byteLength(row.pose);delete row.pose;}
    await writeFile(path.join(cache,'runs',label+'.stdout.txt'),row.stdout||'');
    row.stdout_excerpt=(row.stdout||'').slice(-1800);delete row.stdout;
    evidence.rows.push(row);
    console.log(JSON.stringify(row));
    await writeFile(path.join(out,outputName),JSON.stringify(evidence,null,2)+'\n');
    if(!row.ok)throw new Error(row.error||'Browser docking failed');
  }
} finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
