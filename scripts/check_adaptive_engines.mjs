// Fresh sequential processes prevent engine heaps from contaminating each other.
import {readFile,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {createEngine} from '../research/whole_run_engine.mjs';
import {record,sha,encode} from '../research/whole_run_protocol.mjs';
const folder='docs/evaluation/adaptive_docking_2026-09-08/';
const old=JSON.parse(await readFile('docs/evaluation/docking_whole_runs_2026-09-08/plan.json','utf8'));
const science=JSON.parse(await readFile(folder+'science_inputs.json','utf8'));
const targets=[{target:'old_fa10',maps:old.maps,ligands:old.browser_ligands.map(id=>old.ligands.find(l=>l.id===id))},...science.targets.filter(t=>!t.preparation_failed).map(t=>({...t,ligands:['source','independent'].map(c=>({id:'crystal_'+c,path:t.ligands.find(l=>l.id==='crystal')[c].path}))}))];
if(process.argv[2]==='worker'){
 const variant=process.argv[3],target=targets.find(t=>t.target===process.argv[4]);
 const {default:factory}=await import('../tmp/docking-runs/'+variant+'.mjs');
 const files=await Promise.all(target.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
 const engine=await createEngine(factory,files,await readFile(target.ligands[0].path,'utf8'));const rows=[];
 for(const l of target.ligands){
  const input=await readFile(l.path,'utf8'),load=engine.load(input);
  for(const [i,cap] of [4000,16000].entries()){
   const r=engine.run(104729+13007*i,cap);assert(r.ok);
   rows.push({id:l.id,cap,seed:104729+13007*i,record_sha256:await sha(encode(record(r))),score:r.score,trace_values:r.trace.length,molecular_ms:r.search_ms,call_ms:r.call_ms,load_ms:load,heap_bytes:engine.memory()});
  }
 }
 await writeFile(folder+'equivalence_'+variant+'_'+target.target+'.json',JSON.stringify({variant,target:target.target,init_ms:engine.init_ms,rows},null,2)+'\n');
}else{
 const checks=[];
 for(const t of targets){
  const variants=[];
  for(const v of ['whole_run','whole_run_adaptive','whole_run_type_cache']){
   const p=spawnSync(process.execPath,[process.argv[1],'worker',v,t.target],{stdio:'inherit'});if(p.status!==0)throw Error('Engine comparison worker failed: '+v);
   variants.push(JSON.parse(await readFile(folder+'equivalence_'+v+'_'+t.target+'.json','utf8')));
  }
  for(let i=0;i<variants[0].rows.length;i++)for(const v of variants.slice(1))assert.equal(v.rows[i].record_sha256,variants[0].rows[i].record_sha256,'Score/pose/trace mismatch '+t.target+' '+i+' '+v.variant);
  checks.push({target:t.target,records_per_variant:variants[0].rows.length,exact_score_pose_trace_match:true});console.log('Exact engine equivalence',t.target,variants[0].rows.length);
 }
 await writeFile(folder+'engine_equivalence.json',JSON.stringify({scope:'Exact serialized score/pose/full-trace hashes on selected ligands and seeds. Finite regression evidence, not a proof over all inputs. Single-worker XS Vina only; AD4 excluded.',checks},null,2)+'\n');
}
