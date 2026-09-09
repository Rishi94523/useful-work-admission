// Real Chrome module worker, with trusted local IPC to the Python scheduler.
import {readFile} from 'node:fs/promises';
import {createInterface} from 'node:readline';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
const plan=JSON.parse(await readFile('docs/evaluation/docking_whole_runs_2026-09-08/plan.json','utf8'));
function compute(req){
 const t=performance.now(),n=req.units.length,k=Math.floor(n*req.fraction),solved=new Map();let molecular=0,loads=0,newlyComputed=0;
 for(let i=0;i<n;i++){
  const key=JSON.stringify(req.units[i]);
  if(i<k&&(!req.reuse||!attempted.has(key))){loads+=engine.load(inputs.get(req.units[i].ligand));const r=engine.run(req.units[i].seed,req.units[i].cap);molecular+=r.search_ms;cache.set(key,p.record(r));newlyComputed++;}
  if(req.reuse)attempted.add(key);if(cache.has(key)&&(req.reuse||i<k))solved.set(i,cache.get(key));
 }
 const dummy={score:0,pose:'REMARK omitted work\n',trace:[]},records=req.units.map((u,i)=>solved.get(i)||dummy),before=performance.now();
 return p.commit(req.binding,req.units,records).then(commitment=>({records,commitment,correct_records:solved.size,new_runs:newlyComputed,molecular_ms:molecular,ligand_init_ms:loads,commit_ms:performance.now()-before,total_ms:performance.now()-t,heap_bytes:engine.memory(),science_bytes:p.encode(records).length,commitment_bytes:p.encode(commitment).length}));
}
const workerSource=`import factory from '/whole_run.mjs';import {createEngine} from '/engine.mjs';import * as p from '/protocol.mjs';let engine,inputs;const cache=new Map(),attempted=new Set();${compute.toString()}
self.onmessage=async({data:req})=>{try{if(req.mode==='init'){const t=performance.now();inputs=new Map(req.inputs);const files=await Promise.all(req.maps.map(async m=>({name:m.name,data:new Uint8Array(await(await fetch('/'+m.name)).arrayBuffer())})));const fetched=performance.now();engine=await createEngine(factory,files,inputs.values().next().value);self.postMessage({ready:true,fetch_ms:fetched-t,init_ms:engine.init_ms,heap_bytes:engine.memory()});}else self.postMessage(await compute(req));}catch(e){self.postMessage({error:String(e)});}};`;
const variant=process.env.DOCKING_TYPE_CACHE==='1'?'whole_run_type_cache':'whole_run';
// The generated factory locates its same-stem WASM beside the imported module.
const allowed=new Map([['/whole_run.mjs','tmp/docking-runs/'+variant+'.mjs'],['/'+variant+'.wasm','tmp/docking-runs/'+variant+'.wasm'],['/engine.mjs','research/whole_run_engine.mjs'],['/protocol.mjs','research/whole_run_protocol.mjs']]);for(const m of plan.maps)allowed.set('/'+m.name,m.path);
const server=createServer(async(req,res)=>{const url=new URL(req.url,'http://localhost').pathname;if(url==='/'){res.end('<title>Adaptive molecular worker experiment</title>');return;}if(url==='/worker.mjs'){res.setHeader('Content-Type','text/javascript');res.end(workerSource);return;}if(!allowed.has(url)){res.writeHead(404).end();return;}res.setHeader('Content-Type',url.endsWith('.wasm')?'application/wasm':url.endsWith('.mjs')?'text/javascript':'application/octet-stream');res.end(await readFile(allowed.get(url)));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{
 const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);
 const inputs=await Promise.all(plan.ligands.map(async l=>[l.id,await readFile(l.path,'utf8')]));
 const init=await page.evaluate(async({maps,inputs})=>{window.worker=new Worker('/worker.mjs',{type:'module'});window.ask=req=>new Promise((resolve,reject)=>{worker.onmessage=e=>resolve(e.data);worker.onerror=e=>reject(Error(e.message));worker.postMessage(req);});return await ask({mode:'init',maps,inputs});},{maps:plan.maps,inputs});
 console.log(JSON.stringify({...init,browser:browser.version(),worker:true}));
 for await(const line of createInterface({input:process.stdin,crlfDelay:Infinity})){const req=JSON.parse(line);if(req.mode==='quit')break;console.log(JSON.stringify(await page.evaluate(req=>ask(req),req)));}
}finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
