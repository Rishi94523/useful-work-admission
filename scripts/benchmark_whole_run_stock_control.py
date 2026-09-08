"""Official Vina binary redocking: E8, default refinement, default nine modes."""
import hashlib,json,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-runs';OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
ligand=ROOT/'tmp/docking-audit/ligands/crystal.pdbqt';receptor=ROOT/'tmp/docking-audit/receptor.pdbqt';output=BASE/'stock_crystal.pdbqt';exe=ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'
center=json.loads((ROOT/'docs/evaluation/docking_lightweight_2026-09-07/ligands.json').read_text())['box_center']
args=[str(exe),'--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed','104729','--exhaustiveness','8','--num_modes','9','--out',str(output)]
for axis,c in zip('xyz',center):args+=['--center_'+axis,str(c),'--size_'+axis,'30']
t=time.perf_counter();r=subprocess.run(args,capture_output=True,text=True,timeout=600);wall=(time.perf_counter()-t)*1000
if r.returncode:raise RuntimeError(r.stdout+r.stderr)
pose=output.read_text().split('ENDMDL')[0]+'ENDMDL\n';score=float(re.search(r'REMARK VINA RESULT:\s+([-0-9.]+)',pose).group(1))
record={'scope':'Official Vina1.2.7 stock binary. CPU1, E8, num_modes9, no evaluation cap, default explicit-receptor post-refinement enabled. Same prepared receptor and crystal ligand; includes process/maps/preparation/search.','argv':args,'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'wall_ms':wall,'score':score,'pose':pose,'all_poses_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'stdout':r.stdout,'stderr':r.stderr}
(OUT/'stock_control.json').write_text(json.dumps(record,indent=2)+'\n');print({'stock_control_ms':wall,'score':score})
