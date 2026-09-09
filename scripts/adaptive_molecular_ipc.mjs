// Separate client/server processes use identical pinned WASM. Trusted test IPC.
import {readFile} from 'node:fs/promises';
import {createInterface} from 'node:readline';
const variant=process.env.DOCKING_TYPE_CACHE==='1'?'whole_run_type_cache':'whole_run';
const {default:factory}=await import('../tmp/docking-runs/'+variant+'.mjs');
import {createEngine} from '../research/whole_run_engine.mjs';
import * as p from '../research/whole_run_protocol.mjs';
const plan=JSON.parse(await readFile('docs/evaluation/docking_whole_runs_2026-09-08/plan.json','utf8'));
const inputs=new Map(await Promise.all(plan.ligands.map(async l=>[l.id,await readFile(l.path,'utf8')])));
const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
const engine=await createEngine(factory,files,inputs.get(plan.ligands[0].id));
const cache=new Map(),attempted=new Set();let loads=0,molecular=0;
function run(u){loads+=engine.load(inputs.get(u.ligand));const r=engine.run(u.seed,u.cap);molecular+=r.search_ms;return r;}
console.log(JSON.stringify({ready:true,init_ms:engine.init_ms,heap_bytes:engine.memory()}));
for await(const line of createInterface({input:process.stdin,crlfDelay:Infinity}))try{
 const req=JSON.parse(line);if(req.mode==='quit')break;loads=0;molecular=0;const t=performance.now();
 if(req.mode==='compute'){
  const n=req.units.length,k=Math.floor(n*req.fraction),solved=new Map();let newlyComputed=0;
  for(let i=0;i<n;i++){
   const key=JSON.stringify(req.units[i]);
   if(i<k&&(!req.reuse||!attempted.has(key))){cache.set(key,p.record(run(req.units[i])));newlyComputed++;}
   if(req.reuse)attempted.add(key);
   if(cache.has(key)&&(req.reuse||i<k))solved.set(i,cache.get(key));
  }
  const dummy={score:0,pose:'REMARK omitted work\n',trace:[]};
  const records=req.units.map((u,i)=>solved.get(i)||dummy),before=performance.now(),commitment=await p.commit(req.binding,req.units,records);
  console.log(JSON.stringify({records,commitment,correct_records:solved.size,new_runs:newlyComputed,molecular_ms:molecular,ligand_init_ms:loads,commit_ms:performance.now()-before,total_ms:performance.now()-t,heap_bytes:engine.memory(),science_bytes:p.encode(records).length,commitment_bytes:p.encode(commitment).length}));
 }else if(req.mode==='audit'){
  const checked=await p.audit(req.binding,req.units,req.commitment,req.draws,req.openings,run);
  console.log(JSON.stringify({...checked,molecular_ms:molecular,ligand_init_ms:loads,total_ms:performance.now()-t,heap_bytes:engine.memory(),opening_bytes:p.encode(req.openings).length}));
 }else throw Error('Bad mode');
}catch(e){console.log(JSON.stringify({error:String(e)}));}
