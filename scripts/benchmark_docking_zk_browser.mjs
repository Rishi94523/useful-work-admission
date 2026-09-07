import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const dir=path.resolve('tmp/docking-pilot/zk');
const input=JSON.parse(await readFile(path.join(dir,'input.json'),'utf8'));
const allow=new Map([['/snarkjs.min.js',path.resolve('research/docking-zk/node_modules/snarkjs/build/snarkjs.min.js')]]);
for(const n of [2,8])for(const file of [`contact_${n}_js/contact_${n}.wasm`,'DEVELOPMENT_ONLY.zkey','verification_key.json'])allow.set(`/zk/${n}/${file}`,path.join(dir,String(n),file));
const server=createServer(async(req,res)=>{
  res.setHeader('Cross-Origin-Opener-Policy','same-origin');res.setHeader('Cross-Origin-Embedder-Policy','require-corp');
  if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Development proof calibration</title><script src="/snarkjs.min.js"></script>');return;}
  if(!allow.has(req.url)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':req.url.endsWith('.wasm')?'application/wasm':'application/octet-stream');
  res.end(await readFile(allow.get(req.url)));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);
 const evidence={scope:'Actual local Chromium Groth16 fullProve with one prover thread and local HTTP assets. Single-party development setup; reduced integer contact search, not Vina or scientific validation. Timings include witness/key fetch; JS library load precedes timer.',browser:browser.version(),rows:[]};
 for(const n of [2,8]){
  const row=await page.evaluate(async({n,input})=>{
   const start=performance.now();
   const result=await snarkjs.groth16.fullProve(input,`/zk/${n}/contact_${n}_js/contact_${n}.wasm`,`/zk/${n}/DEVELOPMENT_ONLY.zkey`,undefined,undefined,{singleThread:true});
   const elapsed=performance.now()-start;
   const vk=await fetch(`/zk/${n}/verification_key.json`).then(r=>r.json());
   const checkStart=performance.now();const valid=await snarkjs.groth16.verify(vk,result.publicSignals,result.proof);
   return {n,prove_ms:elapsed,browser_verify_ms:performance.now()-checkStart,valid,proof:result.proof,publicSignals:result.publicSignals,js_heap_snapshot_bytes:performance.memory?.usedJSHeapSize||null};
  },{n,input});
  assert(row.valid);const ref=JSON.parse(await readFile(path.join(dir,String(n),'proof_20260906.json'),'utf8'));assert.deepEqual(row.publicSignals,ref.publicSignals);
  console.log(JSON.stringify({n,prove_ms:row.prove_ms,browser_verify_ms:row.browser_verify_ms,valid:row.valid}));
  evidence.rows.push(row);await writeFile('docs/evaluation/docking_pilot_2026-09-06/zk_browser.json',JSON.stringify(evidence,null,2)+'\n');
 }
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
