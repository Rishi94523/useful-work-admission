// Same unmodified WASM, local files only: no HTTP or network on initialization.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import factory from '../tmp/vina-resources/compact_single/vina_tasks.mjs';
const out='docs/evaluation/vina_startup_2026-09-13';await mkdir(out,{recursive:true});
const target=JSON.parse(await readFile('docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json')).targets.find(t=>t.target==='fa10');
const ligand=target.ligands.find(l=>l.id==='crystal').source;
const receptor=await readFile(target.receptor),ligandBytes=await readFile(ligand.path),wasm=await readFile('tmp/vina-resources/compact_single/vina_tasks.wasm');
const hash=x=>createHash('sha256').update(x).digest('hex');
if(hash(receptor)!==target.receptor_sha256||hash(ligandBytes)!==ligand.sha256)throw Error('Input hash mismatch');
const t0=performance.now(),m=await factory({print:()=>{},printErr:()=>{}}),factory_ms=performance.now()-t0;
m.FS.mkdir('/tasks');m.FS.writeFile('/receptor.pdbqt',receptor);m.FS.writeFile('/ligand.pdbqt',ligandBytes);
const t1=performance.now();const init=JSON.parse(m.ccall('vt_init','string',['number','number','number'],target.center));const init_ms=performance.now()-t1;
if(!init.ok)throw Error('Init failed');
const profile=JSON.parse(m.ccall('vt_profile','string',[],[]));
const at=phase=>profile.find(p=>p.phase===phase).time_ms;
const phases={engine_ms:at('after_engine')-at('before_engine'),receptor_ms:at('after_receptor')-at('after_engine'),ligand_and_pair_tables_ms:at('after_ligand')-at('after_receptor'),maps_and_scoring_setup_ms:at('after_maps')-at('after_ligand'),save_initial_ms:at('after_save')-at('after_maps')};
const result={environment:'Node, local files, no HTTP; one measured initialization; not a phone phase profile',factory_ms,init_ms,phases,profile,wasm_sha256:hash(wasm),asset_bytes:{wasm:wasm.length,receptor:receptor.length,ligand:ligandBytes.length},scope:'Maps phase includes grid population, lazy scoring tables and explicit-receptor non_cache setup. No molecular search performed. No new 64k test.'};
await writeFile(out+'/offline_profile.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({factory_ms,init_ms,phases,asset_bytes:result.asset_bytes},null,2));
