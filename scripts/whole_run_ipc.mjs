// Local trusted orchestration, not an exposed request parser.
import {readFile} from 'node:fs/promises';
import {createInterface} from 'node:readline';
import factory from '../tmp/docking-runs/whole_run.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import * as p from '../research/whole_run_protocol.mjs';
const plan=JSON.parse(await readFile('docs/evaluation/docking_whole_runs_2026-09-08/plan.json','utf8'));
const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)}))),inputs=new Map(await Promise.all(plan.ligands.map(async l=>[l.id,await readFile(l.path,'utf8')])));
const engine=await createEngine(factory,files,inputs.get(plan.ligands[0].id));let current;
function run(u){engine.load(inputs.get(u.ligand));return engine.run(u.seed,u.cap);}
console.log(JSON.stringify({ready:true,init_ms:engine.init_ms}));
for await(const line of createInterface({input:process.stdin,crlfDelay:Infinity})){
 try{
  const req=JSON.parse(line);if(req.mode==='quit')break;
  if(req.mode==='compute'){
   const t=performance.now(),records=req.units.map(u=>p.record(run(u))),computeMs=performance.now()-t,c=await p.commit(req.binding,req.units,records);current={...req,records,c};
   console.log(JSON.stringify({commitment:c,compute_ms:computeMs}));
  }else if(req.mode==='audit'){
   const t=performance.now(),check=await p.audit(current.binding,current.units,current.c,req.draws,req.draws.map(i=>current.records[i]),run);console.log(JSON.stringify({...check,total_ms:performance.now()-t,scientific_status:'provisional'}));
  }else throw Error('Invalid mode');
 }catch(e){console.log(JSON.stringify({error:String(e)}));}
}
