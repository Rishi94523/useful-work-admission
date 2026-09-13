import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gzipSync,brotliCompressSync} from 'node:zlib';
const hash=x=>createHash('sha256').update(x).digest('hex');
const out='docs/evaluation/vina_prepared_2026-09-13';await mkdir(out,{recursive:true});await mkdir('tmp/vina-prepared/artifacts',{recursive:true});
const targets=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.filter(t=>!t.preparation_failed);
const rows=[];
for(const t of targets){
 const ligand=t.ligands.find(l=>l.id==='crystal').source;const receptor=await readFile(t.receptor),ligandData=await readFile(ligand.path);
 if(hash(receptor)!==t.receptor_sha256||hash(ligandData)!==ligand.sha256)throw Error('inputs');
 let artifact;const modes=[];
 for(const mode of ['reference','compute','restore']){
  const {default:factory}=await import('../tmp/'+(mode==='reference'?'vina-resources/compact_single':'vina-prepared')+'/vina_tasks.mjs');
  const m=await factory({print:()=>{},printErr:()=>{}});m.FS.mkdir('/tasks');m.FS.writeFile('/receptor.pdbqt',receptor);m.FS.writeFile('/ligand.pdbqt',ligandData);
  if(mode==='restore')m.FS.writeFile('/prepared.bin',artifact);
  const start=performance.now();const ok=JSON.parse(mode==='restore'?m.ccall('vt_restore','string',[],[]):m.ccall('vt_init','string',['number','number','number'],t.center));const init_ms=performance.now()-start;if(!ok.ok)throw Error('init '+mode);
  if(mode==='compute'){if(!JSON.parse(m.ccall('vt_prepare','string',[],[])).ok)throw Error('prepare');artifact=m.FS.readFile('/prepared.bin');await writeFile('tmp/vina-prepared/artifacts/'+t.target+'.bin',artifact);}
  const tasks=[];
  for(let i=0;i<4;i++){const ts=performance.now();if(!JSON.parse(m.ccall('vt_run','string',['number','number','number','number'],[i,4,256000,104729])).ok)throw Error('task');tasks.push({index:i,pool:hash(m.FS.readFile('/tasks/'+i+'.task')),trace:hash(m.FS.readFile('/tasks/'+i+'.task.trace'))});if(i===0)tasks[0].call_ms=performance.now()-ts;}
  if(!JSON.parse(m.ccall('vt_finalize','string',['number'],[4])).ok)throw Error('finalize');
  modes.push({mode,init_ms,tasks,final_pose_sha256:hash(m.FS.readFile('/final.pdbqt'))});
  if(mode==='restore'){
   for(const bad of [artifact.subarray(0,100),new Uint8Array(artifact.length)]){m.FS.writeFile('/prepared.bin',bad);if(JSON.parse(m.ccall('vt_restore','string',[],[])).ok)throw Error('malformed accepted');}
  }
 }
 const signatures=modes.map(m=>JSON.stringify([m.tasks.map(({call_ms,...x})=>x),m.final_pose_sha256]));if(!signatures.every(s=>s===signatures[0]))throw Error('Scientific regression '+t.target);
 const gz=gzipSync(artifact,{level:9}),br=brotliCompressSync(artifact);await writeFile('tmp/vina-prepared/artifacts/'+t.target+'.bin.gz',gz);
 rows.push({target:t.target,exact:true,modes,artifact:{bytes:artifact.length,sha256:hash(artifact),gzip_bytes:gz.length,brotli_bytes:br.length,receptor_sha256:hash(receptor),ligand_sha256:hash(ligandData),center:t.center,box:[30,30,30],spacing:.5,cap:256000,format:'VPS1 little-endian float64, grid bounds and values plus initialized XS tables; exact-build manifest required'}});
 await writeFile(out+'/equivalence.json',JSON.stringify({scope:'Three source-conformer targets, four 256k units each. Reference vs new compute vs restored build; exact raw pools, traces, original finalizer. Node timings exclude download; malformed header/truncation rejected. Not universal chemical coverage.',rows},null,2)+'\n');console.log(t.target,'EXACT',modes.map(m=>[m.mode,m.init_ms]),'bytes',artifact.length,'gzip',gz.length);
}
