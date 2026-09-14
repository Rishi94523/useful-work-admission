import {sha256} from '/sha.mjs';
let engine;
async function artifactStore(operation,key,value){
 const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('vina-prepared-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('artifacts');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction('artifacts',operation==='get'?'readonly':'readwrite'),store=tx.objectStore('artifacts');const r=operation==='get'?store.get(key):store.put(value,key);let result;r.onsuccess=()=>{result=r.result};tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}
}
onmessage=async({data})=>{try{
 if(data.mode==='finalize'){
  if(!engine)throw Error('Missing finalization engine');
  for(const r of data.runs)engine.FS.writeFile('/tasks/'+r.index+'.task',r.pool);
  const t=performance.now();if(!JSON.parse(engine.ccall('vt_finalize','string',['number'],[4])).ok)throw Error('Finalization failed');
  postMessage({final_pose_sha256:await sha256(engine.FS.readFile('/final.pdbqt')),finalize_ms:performance.now()-t});return;
 }
 const {manifest,mode,index}=data,metrics={mode,index,secure_context:globalThis.isSecureContext===true,hash_backend:globalThis.crypto?.subtle?'webcrypto':'javascript-sha256'};
 if(manifest.require_webcrypto&&metrics.hash_backend!=='webcrypto')throw Error('This test requires HTTPS and native WebCrypto');
 if(mode!=='reuse'){
  const start=performance.now();const {default:factory}=await import(manifest.module_url);
  const cache=manifest.cdn?'default':mode==='cold_restore'?'reload':'force-cache';
  const get=async url=>{const r=await fetch(url,{cache});if(!r.ok)throw Error('Asset '+r.status);(metrics.responses??=[]).push({url,content_encoding:r.headers.get('content-encoding'),content_length:r.headers.get('content-length'),cf_cache_status:r.headers.get('cf-cache-status'),delivery_cache:r.headers.get('x-delivery-cache'),etag:r.headers.get('etag'),age:r.headers.get('age'),cf_ray:r.headers.get('cf-ray')});return new Uint8Array(await r.arrayBuffer());};
  const getArtifact=async()=>{
   if(mode==='compute')return null;
   if(mode==='cached_restore'&&manifest.cache_policy==='indexeddb-v1'){
    const t=performance.now();try{const cached=await artifactStore('get',manifest.artifact_sha256);metrics.artifact_cache_read_ms=performance.now()-t;if(cached){metrics.artifact_cache_source='indexeddb';return new Uint8Array(cached);}}catch(e){metrics.artifact_cache_error=String(e);}
   }
   metrics.artifact_cache_source='http';const bytes=await get(manifest.artifact_url);
   if(manifest.artifact_transform==='shuffle8'){const t=performance.now(),n=Math.floor(bytes.length/8),decoded=new Uint8Array(bytes.length);for(let j=0;j<8;j++)for(let i=0;i<n;i++)decoded[i*8+j]=bytes[j*n+i];decoded.set(bytes.subarray(n*8),n*8);metrics.unshuffle_ms=performance.now()-t;return decoded;}return bytes;
  };
  const [wasm,receptor,ligand,artifact]=await Promise.all([get(manifest.wasm_url),get(manifest.receptor_url),get(manifest.ligand_url),getArtifact()]);
  metrics.assets_ms=performance.now()-start;const hs=performance.now();
  for(const [bytes,expected] of [[wasm,manifest.wasm_sha256],[receptor,manifest.receptor_sha256],[ligand,manifest.ligand_sha256],...(artifact?[[artifact,manifest.artifact_sha256]]:[])])if(await sha256(bytes)!==expected)throw Error('Asset integrity mismatch');
  metrics.hash_ms=performance.now()-hs;
  if(artifact&&manifest.cache_policy==='indexeddb-v1'&&metrics.artifact_cache_source!=='indexeddb'){const t=performance.now();try{await artifactStore('put',manifest.artifact_sha256,artifact.buffer);metrics.artifact_cache_written=true;}catch(e){metrics.artifact_cache_error=String(e);}metrics.artifact_cache_write_ms=performance.now()-t;}
  const fs=performance.now();engine=await factory({wasmBinary:wasm,print:()=>{},printErr:()=>{}});metrics.factory_ms=performance.now()-fs;
  engine.FS.mkdir('/tasks');const copy=performance.now();engine.FS.writeFile('/receptor.pdbqt',receptor);engine.FS.writeFile('/ligand.pdbqt',ligand);if(artifact)engine.FS.writeFile('/prepared.bin',artifact);metrics.fs_copy_ms=performance.now()-copy;
  const init=performance.now();const ok=JSON.parse(mode==='compute'?engine.ccall('vt_init','string',['number','number','number'],manifest.center):engine.ccall('vt_restore','string',[],[]));metrics.init_or_restore_ms=performance.now()-init;if(!ok.ok)throw Error('Initialize/restore failed');
  if(artifact)engine.FS.unlink('/prepared.bin');
  metrics.resources=performance.getEntriesByType('resource').map(r=>({name:r.name.split('?')[0],duration:r.duration,transferSize:r.transferSize,encodedBodySize:r.encodedBodySize,decodedBodySize:r.decodedBodySize}));
 }
 if(!engine)throw Error('Missing reused worker');const start=performance.now();const result=JSON.parse(engine.ccall('vt_run','string',['number','number','number','number'],[index,4,256000,104729]));metrics.run_ms=performance.now()-start;if(!result.ok)throw Error('Run failed');
 postMessage({...metrics,result,heap:engine.ccall('vt_memory','number',[],[]),pool:engine.FS.readFile('/tasks/'+index+'.task',{encoding:'utf8'}),trace:engine.FS.readFile('/tasks/'+index+'.task.trace',{encoding:'utf8'})});
}catch(e){postMessage({error:String(e)});}};
