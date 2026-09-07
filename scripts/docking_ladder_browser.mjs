import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {makeContactReference} from '../research/docking-zk/contact_reference.mjs';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const [count,seed,target]=process.argv.slice(2);const n=Number(count);
const root=path.resolve(n<=8?'tmp/docking-pilot/zk':'tmp/docking-ladder');const base=path.join(root,String(n));
const input={...JSON.parse(await readFile(path.join(root,'input.json'),'utf8')),seed};
const reference=(await makeContactReference())(input,n);
const assets=new Map([['/snarkjs.min.js',path.resolve('research/docking-zk/node_modules/snarkjs/build/snarkjs.min.js')],['/witness.wasm',path.join(base,`contact_${n}_js/contact_${n}.wasm`)],['/key.zkey',path.join(base,'DEVELOPMENT_ONLY.zkey')],['/vk.json',path.join(base,'verification_key.json')]]);
const server=createServer(async(req,res)=>{
 res.setHeader('Cross-Origin-Opener-Policy','same-origin');res.setHeader('Cross-Origin-Embedder-Policy','require-corp');
 if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Proof scaling benchmark</title><script src="/snarkjs.min.js"></script>');return;}
 if(!assets.has(req.url)){res.writeHead(404).end();return;}
 try{res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':req.url.endsWith('.wasm')?'application/wasm':'application/octet-stream');res.end(await readFile(assets.get(req.url)));}catch{res.writeHead(500).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH});
 const page=await browser.newPage();const loading=performance.now();await page.goto('http://127.0.0.1:'+server.address().port);const libraryLoad=performance.now()-loading;
 const row=await page.evaluate(async input=>{
  const start=performance.now();const {proof,publicSignals}=await snarkjs.groth16.fullProve(input,'/witness.wasm','/key.zkey',undefined,undefined,{singleThread:true});const prove=performance.now()-start;
  const key=await fetch('/vk.json').then(r=>r.json());const started=performance.now();const valid=await snarkjs.groth16.verify(key,publicSignals,proof);
  return {prove_ms:prove,cold_browser_verify_ms:performance.now()-started,valid,proof,publicSignals,js_heap_snapshot_bytes:performance.memory?.usedJSHeapSize||null};
 },input);
 assert(row.valid);assert.deepEqual(row.publicSignals,[reference.bestScore,reference.bestIndex,seed,...input.ligand.flat(),...input.receptor.flat()].map(String));
 const output={n,seed,browser:browser.version(),library_load_ms:libraryLoad,proving_key_bytes:(await stat(assets.get('/key.zkey'))).size,...row};
 await writeFile(target,JSON.stringify(output,null,2)+'\n');console.log(JSON.stringify({n,seed,prove_ms:row.prove_ms}));
}finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
process.exit(0);
