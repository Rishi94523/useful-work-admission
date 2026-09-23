const hash=async s=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),b=>b.toString(16).padStart(2,'0')).join('');
export default {async fetch(request,env,ctx){
 const url=new URL(request.url);
 if(/^\/delivery\/[a-f0-9]{64}\.(br|gz)$/.test(url.pathname)&&['GET','HEAD'].includes(request.method)){
  const encoding=url.pathname.endsWith('.br')?'br':'gzip';
  if(!(request.headers.get('Accept-Encoding')||'').includes(encoding))return new Response('Encoding not supported',{status:406});
  const cacheKey=new Request(url.origin+url.pathname),hit=await caches.default.match(cacheKey);
  if(hit){const h=new Headers(hit.headers);h.set('X-Delivery-Cache','HIT');h.set('Content-Encoding',encoding);return new Response(request.method==='HEAD'?null:hit.body,{status:hit.status,headers:h,encodeBody:'manual'});}
  const assetUrl=new URL(request.url);assetUrl.pathname=assetUrl.pathname.replace('/delivery/','/assets/');assetUrl.search='';
  const asset=await env.ASSETS.fetch(new Request(assetUrl,{headers:{'Accept-Encoding':'identity'}}));if(!asset.ok)return asset;
  const h=new Headers(asset.headers);h.set('Content-Type','application/octet-stream');h.set('Content-Encoding',encoding);h.set('Cache-Control','public, max-age=31536000, immutable');h.set('X-Delivery-Cache','MISS');h.delete('Vary');
  const response=new Response(asset.body,{headers:h,encodeBody:'manual'});ctx.waitUntil(caches.default.put(cacheKey,response.clone()));return request.method==='HEAD'?new Response(null,{headers:h}):response;
 }
 if(url.pathname==='/timing-results'){
  // Unit vs puzzle device timing. Units are re-checked here against the
  // expected scientific outputs rather than trusting the page's own flag.
  if(!env.UPLOAD_KEY||url.searchParams.get('key')!==env.UPLOAD_KEY)return new Response('Forbidden',{status:403});
  if(request.method!=='POST')return new Response('Method',{status:405});
  try{
   const reader=request.body.getReader();let total=0,parts=[];for(;;){const {value,done}=await reader.read();if(done)break;total+=value.length;if(total>2000000){await reader.cancel();return new Response('Too large',{status:413});}parts.push(value);}
   const bytes=new Uint8Array(total);let offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}const r=JSON.parse(new TextDecoder().decode(bytes));
   if(typeof r.id!=='string'||!/^[a-f0-9-]{36}$/.test(r.id)||!Array.isArray(r.units)||r.units.length>40||!Array.isArray(r.puzzles)||r.puzzles.length>200)throw Error('Schema');
   const m=await(await env.ASSETS.fetch(new URL('/manifest.json',request.url))).json();let exact=0;
   for(const u of r.units){if(!Number.isInteger(u.index)||u.index<0||u.index>3)throw Error('Index');const e=m.expected.tasks[u.index];if(u.pool_sha256===e.pool&&u.trace_sha256===e.trace)exact++;}
   r.server_checks={units:r.units.length,exact_units:exact,artifact_exact:r.artifact_sha256===m.artifact_sha256,wasm_exact:r.wasm_sha256===m.wasm_sha256};r.received_at=new Date().toISOString();
   await env.RESULTS.put('timing_'+r.id,JSON.stringify(r));return Response.json({units:r.units.length,exact_units:exact},{headers:{'Cache-Control':'no-store'}});
  }catch{return new Response('Invalid report',{status:400});}
 }
 if(url.pathname!=='/results')return new Response('Not found',{status:404});
 if(!env.UPLOAD_KEY||url.searchParams.get('key')!==env.UPLOAD_KEY)return new Response('Forbidden',{status:403});
 if(request.method!=='POST')return new Response('Method',{status:405});
 try{
  const reader=request.body.getReader();let total=0,parts=[];for(;;){const {value,done}=await reader.read();if(done)break;total+=value.length;if(total>2000000){await reader.cancel();return new Response('Too large',{status:413});}parts.push(value);}
  const bytes=new Uint8Array(total);let offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}const r=JSON.parse(new TextDecoder().decode(bytes));
  if(!Array.isArray(r.runs)||r.runs.length>4||typeof r.id!=='string'||!/^[a-f0-9-]{36}$/.test(r.id))throw Error('Schema');
  const m=await(await env.ASSETS.fetch(new URL('/manifest.json',request.url))).json();let matches=0;const indices=new Set();
  for(const run of r.runs){if(!Number.isInteger(run.index)||run.index<0||run.index>3||indices.has(run.index))throw Error('Index');indices.add(run.index);const e=m.expected.tasks[run.index];if(await hash(run.pool)===e.pool&&await hash(run.trace)===e.trace)matches++;}
  const final_exact=r.finalization?.final_pose_sha256===m.expected.final_pose_sha256;
  r.server_checks={matches,runs:r.runs.length,final_exact,artifact_exact:r.artifact_sha256===m.artifact_sha256,wasm_exact:r.wasm_sha256===m.wasm_sha256};r.received_at=new Date().toISOString();
  await env.RESULTS.put('device_'+r.id,JSON.stringify(r));return Response.json({matches,runs:r.runs.length,final_exact},{headers:{'Cache-Control':'no-store'}});
 }catch{return new Response('Invalid report',{status:400});}
}};
