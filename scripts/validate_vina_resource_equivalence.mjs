// Same-runtime exact pools, traces, and original receptor finalization.
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
const targets=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.filter(t=>!t.preparation_failed);
const results=[];
for(const t of targets){
 const byVariant=[];
 for(const variant of ['baseline','compact','compact_single']){
  const {default:factory}=await import('../tmp/vina-resources/'+variant+'/vina_tasks.mjs');const m=await factory({print:()=>{},printErr:()=>{}});
  m.FS.mkdir('/tasks');m.FS.writeFile('/receptor.pdbqt',await readFile(t.receptor,'utf8'));m.FS.writeFile('/ligand.pdbqt',await readFile(t.ligands.find(l=>l.id==='crystal').source.path,'utf8'));
  if(!JSON.parse(m.ccall('vt_init','string',['number','number','number'],t.center)).ok)throw Error('init');
  const tasks=[];for(let i=0;i<4;i++){
   if(!JSON.parse(m.ccall('vt_run','string',['number','number','number','number'],[i,4,64000,104729])).ok)throw Error('run');
   tasks.push({pool:hash(m.FS.readFile('/tasks/'+i+'.task')),trace:hash(m.FS.readFile('/tasks/'+i+'.task.trace'))});
  }
  if(!JSON.parse(m.ccall('vt_finalize','string',['number'],[4])).ok)throw Error('finalize');
  byVariant.push({variant,tasks,final_pose_sha256:hash(m.FS.readFile('/final.pdbqt')),wasm_sha256:hash(await readFile('tmp/vina-resources/'+variant+'/vina_tasks.wasm'))});
 }
 const [a,...others]=byVariant,exact=others.every(b=>JSON.stringify(a.tasks)===JSON.stringify(b.tasks)&&a.final_pose_sha256===b.final_pose_sha256);
 results.push({target:t.target,exact,byVariant});if(!exact)throw Error('Regression '+t.target);
 await writeFile('docs/evaluation/vina_resources_2026-09-10/equivalence.json',JSON.stringify({scope:'Node same WASM runtime. Original full raw pools and explicit-receptor finalization. Three source-conformer targets, four64k tasks each. Chrome raw task checks are separately recorded. Not proof of all possible chemical inputs.',results},null,2)+'\n');console.log(t.target,'exact pools, traces, finalization');
}
