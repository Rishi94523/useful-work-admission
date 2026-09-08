import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import factory from '../tmp/docking-runs/whole_run.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import * as protocol from '../research/whole_run_protocol.mjs';
const root=process.cwd(),out=path.join(root,'docs/evaluation/docking_whole_runs_2026-09-08');
const plan=JSON.parse(await readFile(path.join(out,'plan.json'),'utf8'));
const mode=process.argv.includes('--browser')?'browser':'node',smoke=process.argv.includes('--smoke');
let browser,server,page,engine;
const data={scope:'Same pinned WASM molecular relation. Warm reset/search/serialization and commitment; ligand/map initialization separate. No Internet, production admission or phone measurements.',mode,rows:[],initialization:[]};
async function executeLocal(args){
 const {ligands,runs,cap,rep}=args,units=[],records=[],times=[];let loadMs=0;const begin=performance.now();
 for(const l of ligands){loadMs+=engine.load(l.text);for(let r=0;r<runs;r++){
  const u={ligand:l.id,input:l.input_sha256,seed:plan.seeds[r],cap,engine:plan.engine_hash,run:r};
  const result=engine.run(u.seed,cap);if(!result.ok)throw Error(JSON.stringify(result));
  units.push(u);records.push(protocol.record(result));times.push({search_ms:result.search_ms,call_ms:result.call_ms,evals:result.evals,mc_steps:result.mc_steps});
 }}
 const computeEnd=performance.now(),c=await protocol.commit('benchmark-'+rep,units,records),commitEnd=performance.now();
 return {ligands:ligands.length,runs,cap,rep,units,records,times,commitment:c,load_ms:loadMs,molecular_ms:times.reduce((s,t)=>s+t.search_ms,0),compute_call_ms:times.reduce((s,t)=>s+t.call_ms,0),client_warm_ms:commitEnd-begin-loadMs,client_with_ligand_init_ms:commitEnd-begin,commit_ms:commitEnd-computeEnd,wasm_memory_bytes:engine.memory(),full_scientific_bytes:protocol.encode(records).length,commitment_bytes:protocol.encode(c).length};
}
try{
 plan.engine_hash=JSON.parse(await readFile(path.join(out,'build_wasm.json'),'utf8')).wasm_sha256;
 if(mode==='node'){
  const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
  engine=await createEngine(factory,files,await readFile(plan.ligands[0].path,'utf8'));data.initialization.push({init_ms:engine.init_ms,module_ms:engine.module_ms,rss:process.memoryUsage().rss});
 }else{
  const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
  const allowed=new Map([['/runtime.mjs','tmp/docking-runs/whole_run.mjs'],['/whole_run.wasm','tmp/docking-runs/whole_run.wasm'],['/engine.mjs','research/whole_run_engine.mjs'],['/protocol.mjs','research/whole_run_protocol.mjs']]);
  for(const m of plan.maps)allowed.set('/'+m.name,m.path);
  server=createServer(async(req,res)=>{const url=new URL(req.url,'http://localhost').pathname;if(url==='/'){res.end('<title>Whole-run research benchmark</title>');return;}if(!allowed.has(url)){res.writeHead(404).end();return;}res.setHeader('Content-Type',url.endsWith('.wasm')?'application/wasm':url.endsWith('.mjs')?'text/javascript':'application/octet-stream');res.end(await readFile(allowed.get(url)));});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);data.browser=browser.version();
  data.initialization.push(await page.evaluate(async({plan,ligand})=>{const t=performance.now();window.plan=plan;window.protocol=await import('/protocol.mjs');const factory=(await import('/runtime.mjs')).default;const {createEngine}=await import('/engine.mjs');const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:new Uint8Array(await (await fetch('/'+m.name)).arrayBuffer())})));const fetched=performance.now();window.engine=await createEngine(factory,files,ligand);return {fetch_and_import_ms:fetched-t,init_ms:engine.init_ms,module_ms:engine.module_ms,wasm_memory_bytes:engine.memory()};},{plan,ligand:await readFile(plan.ligands[0].path,'utf8')}));
 }
 const execute=mode==='node'?executeLocal:args=>page.evaluate('('+executeLocal.toString()+')('+JSON.stringify(args)+')');
 const ligandCounts=smoke?[1]:[1,4,16],runCounts=smoke?[2]:[1,4,16],caps=smoke?[1000,4000]:[4000,16000];
 for(const cap of caps)for(const n of ligandCounts)for(const runs of runCounts)for(let rep=0;rep<(smoke?1:3);rep++){
  const ligands=await Promise.all(plan.browser_ligands.slice(0,n).map(async id=>{const l=plan.ligands.find(l=>l.id===id);return {...l,text:await readFile(l.path,'utf8')};}));
  const row=await execute({ligands,runs,cap,rep});data.rows.push(row);
  console.log(JSON.stringify({mode,n,runs,cap,rep,warm_ms:row.client_warm_ms,init_ms:row.load_ms}));
  await writeFile(path.join(out,mode+(smoke?'_smoke':'')+'.json'),JSON.stringify(data,null,2)+'\n');
 }
}finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));}
