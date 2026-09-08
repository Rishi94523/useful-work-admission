"""Single-target, preselected active/decoy comparison and real Vina oracle checks."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import rankdata,spearmanr
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets,SCALE
from research.rigid_grid_search import Grid,score
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'


def auc(labels,energies):
    labels=np.array(labels);r=rankdata(-np.array(energies));n=labels.sum();return float((r[labels].sum()-n*(n+1)/2)/(n*(len(labels)-n)))


def main():
    assets=Assets(BASE/'assets');center=np.array(assets.meta['center_milli']);folder=BASE/'science';folder.mkdir(exist_ok=True)
    rec=json.loads((OUT/'ligands.json').read_text());p=subprocess.Popen([str(BASE/'campaign_grid_worker.exe'),str(BASE/'receptor.pdbqt'),*map(str,rec['box_center']),'30','30','30',str(BASE/'maps/fa10')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def reply():
        while True:
            line=p.stdout.readline()
            if not line:raise RuntimeError('Native oracle stopped')
            try:return json.loads(line)
            except json.JSONDecodeError:
                if line.startswith('{'):raise RuntimeError(f'Malformed native response: {line[:1000]}')
    def call(mode,path,extra=''):
        p.stdin.write(f'{mode} "{Path(path).as_posix()}" {extra}\n');p.stdin.flush();r=reply()
        if not r.get('ok'):raise ValueError(r)
        return r
    ready=reply();results=[];oracle=[];calibration=[]
    progress=OUT/'science_progress.json'
    if progress.exists() and '--fresh' not in sys.argv:
        previous=json.loads(progress.read_text());results=previous['results'];oracle=previous['oracle'];calibration=previous['calibration']
    try:
        for lig in assets.meta['ligands']:
            if any(r['id']==lig['id'] for r in results):continue
            identifier=lig['id'];template=BASE/'ligands'/(identifier+'.pdbqt');call('LOAD',template)
            rows=[]
            for n in [4096,16384,65536]:
                t=time.perf_counter();best=2**62;best_index=-1
                for start in range(0,n,4096):
                    values=assets.evaluate(identifier,start,min(4096,n-start));sums=values.astype(np.int64).sum(axis=1);ix=int(np.argmin(sums))
                    if int(sums[ix])<best:best=int(sums[ix]);best_index=start+ix
                rows.append({'poses':n,'energy':best/SCALE,'best_index':best_index,'search_ms':(time.perf_counter()-t)*1000})
            # Separate warm one-pose and 1024-pose costs for cost calibration.
            costs=[]
            for r in range(5):
                t=time.perf_counter();assets.evaluate(identifier,8192,1024);costs.append((time.perf_counter()-t)*1000)
            calibration.append({'id':identifier,'heavy_atoms':lig['heavy_atoms'],'rotatable_bonds':lig['rotatable_bonds'],'conformers':lig['conformers'],'batch_1024_ms':costs})
            # Native source-conformer oracle: H and macrocycle pseudo-atoms move
            # with the molecule; heavy coordinates equal the integer bank exactly.
            lines=template.read_text().splitlines();atom_ids=[i for i,l in enumerate(lines) if l.startswith(('ATOM','HETATM'))]
            allxyz=np.array([[float(lines[i][k:k+8]) for k in (30,38,46)] for i in atom_ids])
            heavy_ids=[i for i,k in enumerate(atom_ids) if lines[k][77:].strip() not in ('H','HD','G0','G1','G2','G3')]
            original=np.load(BASE/'ligands'/(identifier+'.conformers.npy'))[0];dist=np.linalg.norm(allxyz[heavy_ids,None,:]-original[None,:,:],axis=-1);_,original_order=linear_sum_assignment(dist)
            # Match native heavy ordering from centered conformer coordinates.
            source_center=original.mean(axis=0);native=np.array(lig['conformers_milli'][0])/1000
            dist=np.linalg.norm((allxyz[heavy_ids]-source_center)[:,None,:]-native[None,:,:],axis=-1);_,native_order=linear_sum_assignment(dist)
            maps={t:Grid(BASE/'maps'/f'fa10.{t}.map') for t in set(lig['atom_types'])}
            total=len(lig['conformers_milli'])*128*512;sample=[]
            for i in range(256):
                identity=(i*104729+lig['offset'])%total
                if identity//(128*512)==0:sample.append(i)
                if len(sample)==4:break
            for i in sample:
                identity=(i*104729+lig['offset'])%total;tid=identity%512;ri=(identity//512)%128
                rotation=np.array(assets.meta['rotations'][ri])/1e6;shift=np.array([(tid//8**k)%8*375-1312 for k in range(3)])/1000
                transformed=np.floor(((allxyz-source_center)@rotation.T+center/1000+shift)*1000+.5)/1000
                positions=assets.positions(identifier,[i])[0]/1000;transformed[heavy_ids]=positions[native_order]
                modified=lines.copy()
                for lineidx,xyz in zip(atom_ids,transformed):modified[lineidx]=lines[lineidx][:30]+''.join(f'{v:8.3f}' for v in xyz)+lines[lineidx][54:]
                pose=folder/'oracle.pdbqt';pose.write_text('\n'.join(modified)+'\n');native_result=call('SCORE',pose)
                floating,_=score(maps,lig['atom_types'],positions[None,:,:]);quantized=int(assets.evaluate(identifier,i,1).sum())/SCALE
                oracle.append({'id':identifier,'index':i,'native_grid':native_result['grid_energy'],'float_grid':float(floating[0]),'integer_grid':quantized,'oracle_error':abs(float(floating[0])-native_result['grid_energy']),'quantization_error':abs(float(floating[0])-quantized)})
            vina=[]
            for exhaustiveness in [1,4]:
                out=folder/f'{identifier}_e{exhaustiveness}.pdbqt'
                result=call('DOCK',template,f'{exhaustiveness} 4000 "{out.as_posix()}"')
                check_pose=folder/'check.pdbqt';check_pose.write_text('\n'.join(line for line in out.read_text().splitlines() if not line.startswith(('MODEL','ENDMDL')))+'\n')
                try:
                    check=call('SCORE',check_pose);check_fields={'check_ok':True,'check_ms':check['compute_and_pose_prepare_ms'],'checked_score':check['score']}
                except ValueError as error:
                    if 'outside the grid box' not in str(error):raise
                    check_fields={'check_ok':False,'check_ms':None,'checked_score':None,'check_error':str(error)}
                vina.append({'exhaustiveness':exhaustiveness,'max_evals_per_run':4000,**result,**check_fields,'pose_sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
            result={'id':identifier,'label':lig['label'],'heavy_atoms':lig['heavy_atoms'],'rotatable_bonds':lig['rotatable_bonds'],'discrete':rows,'vina':vina};results.append(result)
            (OUT/'science_progress.json').write_text(json.dumps({'ready':ready,'results':results,'oracle':oracle,'calibration':calibration},indent=2)+'\n');print(identifier,rows[-1]['energy'],vina[-1]['score'],flush=True)
    finally:p.stdin.write('QUIT\n');p.stdin.flush();p.wait(timeout=20)
    labels=np.array([r['label']=='active' for r in results]);comparisons=[];rng=np.random.default_rng(104729)
    for method in ['discrete4096','discrete16384','discrete65536','vina1','vina4']:
        energy=np.array([next(x['energy'] for x in r['discrete'] if x['poses']==int(method[8:])) if method.startswith('discrete') else next(x['score'] for x in r['vina'] if x['exhaustiveness']==int(method[4:])) for r in results])
        intervals=[]
        for _ in range(2000):
            chosen=np.r_[rng.choice(np.where(labels)[0],16),rng.choice(np.where(~labels)[0],16)];intervals.append(auc(labels[chosen],energy[chosen]))
        top=np.argsort(energy,kind='stable')[:4]
        comparisons.append({'method':method,'roc_auc':auc(labels,energy),'stratified_bootstrap_auc_95':np.percentile(intervals,[2.5,97.5]).tolist(),'top4_actives':int(labels[top].sum()),'ef_top4':float(labels[top].mean()/labels.mean())})
    output={'scope':'32 preselected molecules, one target, presumed decoys, capped Vina baselines. No clinical or binding claim. Vina full score and coarse intermolecular-only scores are different objectives. No crystal recovery measurement in this ranking pilot.','results':results,'oracle':oracle,'calibration':calibration,'comparison':comparisons,'max_oracle_error':max(r['oracle_error'] for r in oracle),'max_quantization_error':max(r['quantization_error'] for r in oracle)}
    (OUT/'science.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(comparisons))

if __name__=='__main__':main()
