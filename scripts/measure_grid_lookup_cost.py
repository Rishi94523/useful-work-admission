"""Compile one authenticated ROM access to estimate naive grid proof costs."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.process_measure import measured_run
from scripts.prepare_docking_ladder import r1cs_header
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder/lookup';BASE.mkdir(exist_ok=True)
command=[str(ROOT/'tmp/docking-pilot/circom.exe'),str(ROOT/'research/docking-zk/circuits/grid_lookup_cost.circom'),'--r1cs','--O2','-l',str(ROOT/'research/docking-zk/node_modules'),'-o',str(BASE)]
measurement=measured_run(command,BASE/'compile.log')
if measurement['exit_code']!=0:raise RuntimeError((BASE/'compile.log').read_text())
header=r1cs_header(BASE/'grid_lookup_cost.r1cs')
evidence={'scope':'Actual compiled constraint count for one 20-level Poseidon authentication path. Full molecular circuits below are unimplemented projections with independent paths; multiproofs/lookups can change cost. No proving time inferred from this gadget.','gadget':header,'measurement':measurement,'naive_path_constraints_per_pose':[{'heavy_atoms':a,'constraints_paths_only':8*a*header['constraints']} for a in [19,34,38]]}
(ROOT/'docs/evaluation/docking_ladder_2026-09-07/grid_lookup_cost.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
