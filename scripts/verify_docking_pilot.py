"""Replay real poses, quantify complete warm checking and test effort-cheating."""
from pathlib import Path
import json
import math
import random
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.docking_pilot import ROOT,CACHE,EVIDENCE,CASES,case_spec,save_result,first_pose
from research.docking_contract import NativeScorer,PoseContract,atoms,check_candidate


def changed_coordinate(text,value,axis=0):
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if line.startswith(('ATOM  ','HETATM')):
            start=30+axis*8;lines[i]=line[:start]+f'{value:8.3f}'+line[start+8:];break
    return '\n'.join(lines)+'\n'


def main():
    native=json.loads((EVIDENCE/'native_scaling.json').read_text())['rows']
    browser=json.loads((EVIDENCE/'browser_scaling.json').read_text())['rows']
    if (EVIDENCE/'browser_full_search.json').exists():browser+=json.loads((EVIDENCE/'browser_full_search.json').read_text())['rows']
    evidence={'scope':'Single persistent native Vina 1.2.7 scorer per receptor; local IPC/file transport. Full measured check includes pose preflight, canonical reconstruction, write, atom preparation and native score. No HTTP, authentication, deployment or production queue guarantee.', 'score_tolerance_kcal_per_mol':0.05,'cases':[],'attacks':[]}
    for case in CASES:
        spec=case_spec(case);contract=PoseContract(spec)
        scorer=NativeScorer(spec)
        records=[]
        try:
            candidates=[dict(x,engine='native') for x in native if x['case']==spec['id'] and x.get('pose_path')]
            candidates += [dict(x,engine='browser') for x in browser if x['case']==spec['id'] and x.get('pose_path')]
            random.Random(20260906).shuffle(candidates)
            for item in candidates:
                raw=(ROOT/item['pose_path']).read_text()
                begin=time.perf_counter()
                canonical,xyz,digest=contract.validate(raw)
                prepared=time.perf_counter()
                canonical_path=CACHE/'runs/validated.pdbqt';canonical_path.write_text(canonical,encoding='ascii')
                result=scorer.request(canonical_path)
                complete=time.perf_counter()
                if not result['ok']:
                    records.append(dict(id=item.get('id',item['pose_path']),engine=item['engine'],native_rejected=True,reason=result.get('error','engine_error'),complete_check_ms=(complete-begin)*1000))
                    continue
                claimed=item.get('score')
                if claimed is None:
                    import re
                    claimed=float(re.search(r'REMARK VINA RESULT:\s*([-+\d.]+)',raw).group(1))
                assert abs(claimed-result['score'])<=evidence['score_tolerance_kcal_per_mol'],(item,claimed,result)
                records.append(dict(id=item.get('id',item['pose_path']),engine=item['engine'],claimed=claimed,recomputed=result['score'],error=abs(claimed-result['score']),preflight_ms=(prepared-begin)*1000,complete_check_ms=(complete-begin)*1000,**result))
            # Same trusted native library and warmed maps for the central search baseline.
            warm_search=[]
            for effort in [1,2,4,8]:
                for repeat in range(3):
                    r=scorer.request(CACHE/'inputs'/spec['ligand'],mode='D',exhaustiveness=effort,max_evals=1000,output=CACHE/'runs/warm-search.pdbqt')
                    warm_search.append(dict(exhaustiveness=effort,max_evals=1000,repeat=repeat,**r))
            base=next(x for x in candidates if x['engine']=='native' and x['max_evals']==1000 and x['exhaustiveness']==1)
            raw=(ROOT/base['pose_path']).read_text()
            canonical,xyz,_=contract.validate(raw)
            p=CACHE/'runs/attack-valid-low-effort.pdbqt';p.write_text(canonical)
            score=scorer.request(p)['score']
            # A fresh high-effort assignment does not change the pose-score predicate.
            low_effort_check=check_candidate(contract,scorer,raw,score)
            assert low_effort_check['accepted']
            evidence['attacks'].append({'case':spec['id'],'test':'low_effort_pose_claimed_as_high_effort','performed_exhaustiveness':1,'performed_max_evals':1000,'claimed_exhaustiveness':8,'claimed_max_evals':0,'fresh_task_seed':999983,'accepted_by_pose_score_predicate':low_effort_check['accepted'],'score':score,'meaning':'Correct pose scoring does not bind the requested search budget or random seed.'})
            wrong_score_check=check_candidate(contract,scorer,raw,score-100)
            assert not wrong_score_check['accepted'] and wrong_score_check['scorer_called']
            evidence['attacks'].append({'case':spec['id'],'test':'invented_score','claimed':score-100,'actual':score,'rejected':not wrong_score_check['accepted'],'predicate_result':wrong_score_check})
            mutations={
                'nan_coordinate':changed_coordinate(raw,float('nan')),
                'outside_box':changed_coordinate(raw,1000),
                'distorted_geometry':changed_coordinate(raw,xyz[0,0]+1.0),
                'missing_atom':'\n'.join(line for line in raw.splitlines() if not (line.startswith(('ATOM  ','HETATM')) and int(line[6:11])==atoms(raw)[0][0]))+'\n',
                'oversized':raw+' '*17000,
                'altered_torsion_count':raw.replace('TORSDOF','TORSDOF 999 #'),
            }
            for label,payload in mutations.items():
                begin=time.perf_counter();reason=None
                try:contract.validate(payload)
                except (ValueError,UnicodeError,StopIteration) as exc:reason=str(exc)
                evidence['attacks'].append({'case':spec['id'],'test':label,'rejected_before_scoring':reason is not None,'reason':reason,'ms':(time.perf_counter()-begin)*1000})
                assert reason is not None,(spec['id'],label)
            # Small rigid translations produce different hashes but almost identical poses.
            translated=canonical.splitlines();idx=0
            for i,line in enumerate(translated):
                if line.startswith(('ATOM  ','HETATM')):
                    translated[i]=line[:30]+f'{xyz[idx,0]+.002:8.3f}'+line[38:];idx+=1
            shifted='\n'.join(translated)+'\n'
            _,shift_xyz,shift_hash=contract.validate(shifted)
            _,_,original_hash=contract.validate(canonical)
            shift_check=check_candidate(contract,scorer,shifted,score)
            evidence['attacks'].append({'case':spec['id'],'test':'cached_pose_tiny_translation','passes_geometry':True,'different_exact_hash':shift_hash!=original_hash,'passes_score_check':shift_check['accepted'],'predicate_result':shift_check,'pose_rmsd_angstrom':float(((shift_xyz[contract.heavy]-xyz[contract.heavy])**2).sum(axis=1).mean()**.5),'meaning':'Exact hashes alone do not establish a novel useful pose; clustering is required.'})
            accepted=[r for r in records if not r.get('native_rejected')]
            case_record={'case':spec['id'],'atoms':len(contract.ref_atoms),'heavy_atoms':int(contract.heavy.sum()),'setup':scorer.setup,'verification':records,'warm_search':warm_search,'native_rejected_count':len(records)-len(accepted),'max_score_error':max(r['error'] for r in accepted),'mean_complete_check_ms':statistics.mean(r['complete_check_ms'] for r in records),'mean_native_score_ms':statistics.mean(r['compute_ms'] for r in accepted)}
            evidence['cases'].append(case_record)
            save_result('verification.json',evidence)
            print({k:v for k,v in case_record.items() if k not in ['verification','warm_search']},flush=True)
        finally:scorer.close()


if __name__=='__main__':main()
