import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gzipSync,gunzipSync,brotliCompressSync,brotliDecompressSync,constants} from 'node:zlib';
const out='docs/evaluation/vina_cdn_2026-09-14',dir='tmp/vina-cdn/public';
await mkdir(out,{recursive:true});await mkdir(dir+'/assets',{recursive:true});
const hash=b=>createHash('sha256').update(b).digest('hex');
const prior=JSON.parse(await readFile('docs/evaluation/vina_prepared_2026-09-13/equivalence.json'));
if(prior.rows.length!==3||prior.rows.some(r=>!r.exact))throw Error('Reference equivalence');
const ref=prior.rows.find(r=>r.target==='fa10'),raw=await readFile('tmp/vina-prepared/artifacts/fa10.bin');
if(hash(raw)!==ref.artifact.sha256)throw Error('Artifact changed');
const shuffled=Buffer.alloc(raw.length),n=Math.floor(raw.length/8);
for(let j=0;j<8;j++)for(let i=0;i<n;i++)shuffled[j*n+i]=raw[i*8+j];raw.copy(shuffled,n*8,n*8);
const rows=[];let headers='/assets/*\n  Cache-Control: public, max-age=31536000, immutable\n  X-Content-Type-Options: nosniff\n  Access-Control-Expose-Headers: ETag, Content-Length, Content-Encoding, CF-Cache-Status, CF-Ray, Age\n';
for(const [transform,data] of [['identity',raw],['shuffle8',shuffled]])for(const codec of ['gzip9','br5','br9']){
 const t=performance.now(),br=codec.startsWith('br'),packed=br?brotliCompressSync(data,{params:{[constants.BROTLI_PARAM_QUALITY]:Number(codec.slice(2))}}):gzipSync(data,{level:9}),encode_ms=performance.now()-t;
 const dt=performance.now(),decoded=br?brotliDecompressSync(packed):gunzipSync(packed),restored=Buffer.alloc(raw.length);
 if(transform==='identity')decoded.copy(restored);else{for(let j=0;j<8;j++)for(let i=0;i<n;i++)restored[i*8+j]=decoded[j*n+i];decoded.copy(restored,n*8,n*8);}
 if(hash(restored)!==hash(raw))throw Error('Non-lossless transport');
 const name=transform+'-'+codec,url='/assets/'+hash(packed)+'.'+(br?'br':'gz');await writeFile(dir+url,packed);
 headers+=url+'\n  Content-Type: application/octet-stream\n  Content-Encoding: '+(br?'br':'gzip')+'\n';
 rows.push({name,url:url.replace('/assets/','/delivery/'),transform,codec,bytes:packed.length,encode_ms,decode_and_unshuffle_ms:performance.now()-dt,restored_sha256:hash(restored)});
 console.log(name,packed.length);
}
const manifest=JSON.parse(await readFile('docs/evaluation/vina_prepared_2026-09-13/device_manifest.json'));
for(const [key,path] of [['wasm_url','tmp/vina-prepared/vina_tasks.wasm'],['module_url','tmp/vina-prepared/vina_tasks.mjs']]){const b=await readFile(path),url='/assets/'+hash(b)+(key==='module_url'?'.mjs':'.wasm');await writeFile(dir+url,b);manifest[key]=url;}
const inputs=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.find(t=>t.target==='fa10');
for(const [key,path] of [['receptor',inputs.receptor],['ligand',inputs.ligands.find(l=>l.id==='crystal').source.path]]){const b=await readFile(path);if(hash(b)!==manifest[key+'_sha256'])throw Error('Input changed');const url='/assets/'+hash(b)+'.pdbqt';await writeFile(dir+url,b);manifest[key+'_url']=url;}
manifest.variants=rows;manifest.transport_experiment='static-edge-v1';manifest.cdn=true;manifest.require_webcrypto=true;manifest.expected=ref.modes.find(m=>m.mode==='reference');
await writeFile(dir+'/manifest.json',JSON.stringify(manifest));
await writeFile(dir+'/_headers',headers+'\n/\n  Cache-Control: no-store\n/manifest.json\n  Cache-Control: no-store\n');
await copyFile('research/prepared_sha256.mjs',dir+'/sha.mjs');await copyFile('research/prepared_device_worker.mjs',dir+'/worker.mjs');await copyFile('research/cdn_device_page.html',dir+'/index.html');
await writeFile(out+'/compression.json',JSON.stringify({artifact_sha256:hash(raw),raw_bytes:raw.length,rows},null,2)+'\n');
await writeFile(out+'/manifest.json',JSON.stringify(manifest,null,2)+'\n');
