// Actual server-side warm WASM replay of the frozen 256k units, not native timing.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const hash=b=>createHash('sha256').update(b).digest('hex'),out='local-research/admission-2026-09-14';await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile('docs/evaluation/vina_cdn_2026-09-14/manifest.json'));
const inputs=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.find(t=>t.target==='fa10');
const {default:factory}=await import('../tmp/vina-prepared/vina_tasks.mjs');const m=await factory({print:()=>{},printErr:()=>{}});m.FS.mkdir('/tasks');
const wasm=await readFile('tmp/vina-prepared/vina_tasks.wasm');if(hash(wasm)!==manifest.wasm_sha256)throw Error('Engine changed');
m.FS.writeFile('/receptor.pdbqt',await readFile(inputs.receptor));m.FS.writeFile('/ligand.pdbqt',await readFile(inputs.ligands.find(l=>l.id==='crystal').source.path));
const artifact=await readFile('tmp/vina-prepared/artifacts/fa10.bin');if(hash(artifact)!==manifest.artifact_sha256)throw Error('Artifact changed');m.FS.writeFile('/prepared.bin',artifact);
let start=performance.now();if(!JSON.parse(m.ccall('vt_restore','string',[],[])).ok)throw Error('Restore');const restore_ms=performance.now()-start;
const rows=[];for(let i=0;i<4;i++){start=performance.now();const result=JSON.parse(m.ccall('vt_run','string',['number','number','number','number'],[i,4,256000,104729]));const ms=performance.now()-start;const pool=m.FS.readFile('/tasks/'+i+'.task'),trace=m.FS.readFile('/tasks/'+i+'.task.trace');const e=manifest.expected.tasks[i];if(!result.ok||hash(pool)!==e.pool||hash(trace)!==e.trace)throw Error('Replay mismatch');rows.push({index:i,ms,payload_bytes:pool.length+trace.length,exact:true});}
start=performance.now();if(!JSON.parse(m.ccall('vt_finalize','string',['number'],[4])).ok||hash(m.FS.readFile('/final.pdbqt'))!==manifest.expected.final_pose_sha256)throw Error('Finalizer');
const result={restore_ms,rows,finalize_ms:performance.now()-start,final_exact:true,scope:'Four actual 256k warm server WASM replays on this laptop during ranking load. Not isolated capacity or production server hardware. Restore separately amortized.'};await writeFile(out+'/replay_timing.json',JSON.stringify(result,null,2)+'\n');console.log(result);
