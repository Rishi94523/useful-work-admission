import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
const require=createRequire(import.meta.url),{chromium}=require('C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const variant=process.argv[2]||'baseline',targetName=process.argv[3]||'fa10';
if(!['baseline','moves','compact','compact_single'].includes(variant))throw Error('variant');
const out='docs/evaluation/vina_resources_2026-09-10/',prefix=out+variant+'_'+targetName;
await mkdir(out,{recursive:true});
const target=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.find(t=>t.target===targetName),ligand=target.ligands.find(l=>l.id==='crystal').source;
const inputs={receptor:await readFile(target.receptor,'utf8'),ligand:await readFile(ligand.path,'utf8'),center:target.center};
const hash=x=>createHash('sha256').update(x).digest('hex');
if(hash(inputs.receptor)!==target.receptor_sha256||hash(inputs.ligand)!==ligand.sha256)throw Error('inputs');
const worker=`import factory from '/vina_tasks.mjs';let m;onmessage=async({data:r})=>{try{if(r.init){const start=performance.now();m=await factory({print:()=>{},printErr:()=>{}});const module_ms=performance.now()-start;m.FS.mkdir('/tasks');m.FS.writeFile('/receptor.pdbqt',r.inputs.receptor);m.FS.writeFile('/ligand.pdbqt',r.inputs.ligand);const t=performance.now();const result=JSON.parse(m.ccall('vt_init','string',['number','number','number'],r.inputs.center));postMessage({...result,module_ms,init_ms:performance.now()-t,profile:JSON.parse(m.ccall('vt_profile','string',[],[]))});}else{const t=performance.now();const result=JSON.parse(m.ccall('vt_run','string',['number','number','number','number'],[r.index,r.n,r.cap,104729]));const pool=m.FS.readFile('/tasks/'+r.index+'.task',{encoding:'utf8'}),trace=m.FS.readFile('/tasks/'+r.index+'.task.trace',{encoding:'utf8'});postMessage({...result,wall_ms:performance.now()-t,pool,trace,profile:JSON.parse(m.ccall('vt_profile','string',[],[]))});}}catch(e){postMessage({error:String(e)});}};`;
const server=createServer(async(req,res)=>{if(req.url==='/'){res.end('<title>Isolated Vina memory probe</title>');return;}if(req.url==='/worker.mjs'){res.setHeader('Content-Type','text/javascript');res.end(worker);return;}if(!['/vina_tasks.mjs','/vina_tasks.wasm'].includes(req.url)){res.writeHead(404).end();return;}res.setHeader('Content-Type',req.url.endsWith('wasm')?'application/wasm':'text/javascript');res.end(await readFile('tmp/vina-resources/'+variant+req.url));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser,sampler;
try{
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);const cdp=await browser.newBrowserCDPSession();
 const pids=async()=>await writeFile(prefix+'_pids.json',JSON.stringify((await cdp.send('SystemInfo.getProcessInfo')).processInfo));await pids();
 sampler=spawn('python',['scripts/sample_windows_working_set.py',prefix+'_pids.json',prefix+'_working_set.json'],{stdio:['pipe','inherit','inherit'],windowsHide:true});
 await page.evaluate(()=>{const w=new Worker('/worker.mjs',{type:'module'});window.ask=req=>new Promise((resolve,reject)=>{w.onmessage=e=>resolve(e.data);w.onerror=e=>reject(Error(e.message));w.postMessage(req);});});
 const init=await page.evaluate(inputs=>ask({init:true,inputs}),inputs);if(!init.ok)throw Error(JSON.stringify(init));await pids();console.log(variant,targetName,'init',init.init_ms,init.profile.at(-1));
 const runs=[];for(const [index,n,cap] of [[0,4,64000],[1,4,64000],[2,4,256000],[3,4,0],[0,128,64000]]){
  const r=await page.evaluate(req=>ask(req),{index,n,cap});if(!r.ok)throw Error(JSON.stringify(r));await pids();const {pool,trace,...metrics}=r;runs.push({index,n,cap,...metrics,pool_sha256:hash(pool),trace_sha256:hash(trace)});
 }
 await writeFile(prefix+'.json',JSON.stringify({variant,target:targetName,browser:browser.version(),init,runs,input_hashes:{receptor:hash(inputs.receptor),ligand:hash(inputs.ligand)},wasm_sha256:hash(await readFile('tmp/vina-resources/'+variant+'/vina_tasks.wasm'))},null,2)+'\n');
}finally{if(sampler){const done=new Promise(r=>sampler.on('exit',r));sampler.stdin.end('\n');await done;}if(browser)await browser.close();await new Promise(r=>server.close(r));}
