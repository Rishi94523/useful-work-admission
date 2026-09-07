"""Validate quantized finite search against actual Vina maps and its oracle."""
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.docking_pilot import CASES,case_spec,CACHE
from research.rigid_grid_search import Grid,poses,score,SCALE,SPACE
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'


def atom_lines(text):
    return [line for line in text.splitlines() if line.startswith(('ATOM  ','HETATM'))]


def main():
    evidence={'scope':'Real Vina receptor maps, fixed ligand conformers, 24 cubic rotations and 512 translations. Quantization/ranking and native oracle agreement only; not scientific screening validation, not a proof system. Python timings exclude preparation/loading; candidate generation and scoring included.', 'cases':[]}
    for case in CASES:
        spec=case_spec(case);folder=BASE/'grids'/case[0];folder.mkdir(parents=True,exist_ok=True);prefix=folder/'receptor'
        cmd=[str(BASE/'docking_grid_export.exe'),str(CACHE/'inputs'/spec['receptor']),str(CACHE/'inputs'/spec['ligand'])]
        cmd += [str(spec['params'][axis+'_'+k]) for axis in ['center','size'] for k in 'xyz']+[str(prefix)]
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            meta=json.loads(proc.stdout.readline());types=[a['type'] for a in meta['atoms']];xyz=np.array([a['xyz'] for a in meta['atoms']])
            begin=time.perf_counter();maps={t:Grid(str(prefix)+'.'+t+'.map') for t in set(types)};load_ms=(time.perf_counter()-begin)*1000
            # Public example ligands start near the origin; place their centroid
            # at the assigned pocket center before enumerating rigid poses.
            placement=next(iter(maps.values())).center-xyz.mean(axis=0)
            xyz=xyz+placement
            ids,bank=poses(xyz,SPACE,20260907);floating,valid=score(maps,types,bank);integer,valid_int=score(maps,types,bank,True)
            assert np.array_equal(valid,valid_int)
            errors=np.abs(floating[valid]-integer[valid]/SCALE)
            float_order=np.argsort(floating,kind='stable');int_order=np.argsort(integer,kind='stable')
            template=(CACHE/'inputs'/spec['ligand']).read_text();all_xyz=np.array([[float(line[k:k+8]) for k in [30,38,46]] for line in atom_lines(template)])+placement
            # Use the heavy-atom centroid in both the atom-typed evaluator and
            # full PDBQT transform. Hydrogens must rotate with the same origin.
            from research.rigid_grid_search import rotations
            tests=[]
            chosen=list(dict.fromkeys([int(float_order[0]),int(int_order[0])]+np.linspace(0,SPACE-1,24,dtype=int).tolist()))
            for index in chosen:
                if not valid[index]:continue
                identity=int(ids[index]);tid=identity%512;translation=np.array([(tid//8**k)%8-3 for k in range(3)])*.375
                transformed=(all_xyz-xyz.mean(axis=0))@rotations()[identity//512].T+xyz.mean(axis=0)+translation
                transformed=np.floor(transformed*1000+.5)/1000
                lines=[];i=0
                for line in template.splitlines():
                    if line.startswith(('ATOM  ','HETATM')):
                        line=line[:30]+''.join(f'{v:8.3f}' for v in transformed[i])+line[54:];i+=1
                    lines.append(line)
                pose_path=folder/f'oracle_{index}.pdbqt';pose_path.write_text('\n'.join(lines)+'\n')
                proc.stdin.write(str(pose_path)+'\n');proc.stdin.flush();response=json.loads(proc.stdout.readline())
                if not response['ok']:raise RuntimeError('Independent Vina rejected generated in-box pose')
                tests.append({'candidate_index':index,'pose_id':identity,'python_grid_energy':float(floating[index]),'native_grid_energy':response['energies'][1],'absolute_error':abs(float(floating[index])-response['energies'][1])})
            rows=[]
            for n in [16,32,64,128,256,1024,4096,SPACE]:
                samples=[]
                for repeat in range(7):
                    begin=time.perf_counter();_,positions=poses(xyz,n,20260907);values,inside=score(maps,types,positions,True);best=int(np.argmin(values));elapsed=(time.perf_counter()-begin)*1000
                    if repeat:samples.append(elapsed)
                checks=[]
                for repeat in range(21):
                    begin=time.perf_counter();score(maps,types,positions[best:best+1],True);elapsed=(time.perf_counter()-begin)*1000
                    if repeat:checks.append(elapsed)
                rows.append({'n':n,'search_ms':samples,'median_search_ms':statistics.median(samples),'one_pose_check_ms_median':statistics.median(checks),'best_index':best,'best_quantized_energy':int(values[best]),'valid_candidates':int(inside.sum())})
            row={'case':case[0],'heavy_atoms':len(types),'preparation_export_reload_ms':meta['preparation_ms'],'python_load_ms':load_ms,'space':SPACE,'valid_in_box':int(valid.sum()),'map_files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.glob('*.map'))], 'max_quantization_error':float(errors.max()),'median_quantization_error':float(np.median(errors)),'best_pose_agrees':bool(float_order[0]==int_order[0]),'top10_overlap':len(set(map(int,float_order[:10])) & set(map(int,int_order[:10]))),'oracle':tests,'max_oracle_error':max(t['absolute_error'] for t in tests),'timings':rows}
            evidence['cases'].append(row);(OUT/'rigid_grid.json').write_text(json.dumps(evidence,indent=2)+'\n')
            print(json.dumps({k:row[k] for k in ['case','heavy_atoms','valid_in_box','max_quantization_error','best_pose_agrees','top10_overlap','max_oracle_error']}),flush=True)
        finally:
            if proc.poll() is None:
                proc.stdin.write('QUIT\n');proc.stdin.flush();proc.wait(timeout=10)
            if proc.returncode:raise RuntimeError(proc.stderr.read())


if __name__=='__main__':main()
