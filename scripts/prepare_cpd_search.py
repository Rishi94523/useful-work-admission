"""Extract a scientific discrete search model and generate exact Circom circuits."""
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.cpd_search import read_model,restrict_binary,energy,direct_energy,search
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder/cpd';OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'
model=read_model(BASE/'1BK2.wcsp');restricted=restrict_binary(model)
rng=random.Random(20260907)
width=restricted['positions']
for identity in [0,2**width-1]+[rng.randrange(2**width) for _ in range(1000)]:
    assert energy(restricted,identity)==direct_energy(model,restricted,identity)
(OUT/'cpd_restricted_model.json').write_text(json.dumps(restricted,indent=2)+'\n')
# Strings preserve exact large integers when JavaScript reads the witness model.
exact={k:([str(v) for v in value] if k=='linear' else [[str(v) for v in row] for row in value] if k=='pairs' else str(value) if k in ['constant','upper'] else value) for k,value in restricted.items()}
(BASE/'model_exact.json').write_text(json.dumps(exact,indent=2)+'\n')
for n in [16,64]:
    folder=BASE/str(n);folder.mkdir(exist_ok=True)
    terms=[str(restricted['constant'])]+[f'({a})*state[i].out[{j}]' for j,a in enumerate(restricted['linear']) if a]
    products=[]
    for a in range(width):
        for b in range(a+1,width):
            coefficient=restricted['pairs'][a][b]
            if coefficient:
                index=len(products);products.append(f'product[i][{index}] <== state[i].out[{a}]*state[i].out[{b}];')
                terms.append(f'({coefficient})*product[i][{index}]')
    # Raw nonnegative sum <= 300*UB <2^72. Range checks protect comparisons
    # from field wrap; the constant energy polynomial is exact on binary states.
    source='''pragma circom 2.2.3;
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";
template Search() {
signal input start;
signal output bestScore; signal output bestIndex;
component startBound=Num2Bits(WIDTH); startBound.in <== start;
component state[N]; component rawBound[N]; component feasible[N]; component better[N];
signal product[N][P]; signal raw[N]; signal value[N]; signal best[N+1]; signal index[N+1];
best[0] <== UB; index[0] <== 0;
for(var i=0;i<N;i++) {
state[i]=Num2Bits(32); state[i].in <== start+65537*i;
PRODUCTS
raw[i] <== ENERGY;
rawBound[i]=Num2Bits(72); rawBound[i].in <== raw[i];
feasible[i]=LessThan(73); feasible[i].in[0] <== raw[i]; feasible[i].in[1] <== UB;
value[i] <== UB+feasible[i].out*(raw[i]-UB);
better[i]=LessThan(73); better[i].in[0] <== value[i]; better[i].in[1] <== best[i];
best[i+1] <== best[i]+better[i].out*(value[i]-best[i]);
index[i+1] <== index[i]+better[i].out*(i-index[i]);
}
bestScore <== best[N];bestIndex <== index[N];
}
component main {public [start]} = Search();
'''
    import re
    def balanced_sum(entries):
        if len(entries)==1:return entries[0]
        middle=len(entries)//2
        return '('+balanced_sum(entries[:middle])+'+'+balanced_sum(entries[middle:])+')'
    for token,value in [('PRODUCTS','\n'.join(products)),('ENERGY',balanced_sum(terms)),('UB',str(restricted['upper'])),('WIDTH',str(width)),('N',str(n)),('P',str(len(products)))]:source=re.sub(r'\b'+token+r'\b',lambda _:value,source)
    (folder/'main.circom').write_text('// Published restricted model SHA256: '+restricted['model_sha256']+'\n'+source)
print(json.dumps({'positions':width,'pair_products':len(products),'model_sha256':restricted['model_sha256'],'direct_vs_polynomial_checks':1002,'example_64':search(restricted,64,20260907%(2**width))}))
