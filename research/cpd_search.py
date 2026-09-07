"""Exact bounded search in a restricted, published protein-design model.

WCSP costs are integers. The upper bound denotes forbidden assignments.
Restricting to at most two states per site is a pilot subproblem, not full protein design.
"""
import hashlib
import json
from pathlib import Path


def read_model(path):
    with Path(path).open() as f:
        name,n,max_domain,n_functions,upper=f.readline().split();n=int(n);upper=int(upper)
        domains=list(map(int,f.readline().split()));assert len(domains)==n
        functions=[]
        for _ in range(int(n_functions)):
            header=list(map(int,next(f).split()));arity=header[0]
            assert arity in [0,1,2], 'Pilot supports unary/pairwise energies'
            scope=header[1:1+arity];default,count=header[1+arity:]
            assert 0<=default<=upper
            values={}
            for _ in range(count):
                row=list(map(int,next(f).split()));assert len(row)==arity+1
                assert 0<=row[-1]<=upper
                assert all(0<=value<domains[site] for site,value in zip(scope,row[:-1]))
                values[tuple(row[:-1])]=row[-1]
            functions.append((scope,default,values))
        assert not f.read().strip(), 'Unexpected trailing model data'
    return {'name':name,'n':n,'domains':domains,'upper':upper,'functions':functions}


def restrict_binary(model):
    # Published first feasible incumbent, not a new solution found by this pilot.
    # Starting with independent unary minima made two whole pair tables forbidden.
    anchor=[170,2,4,4,3,6,4,116,0,114,5,4,15,19,4,6,5,116,1,0,28,0,22,4]
    def original_cost(choice):
        return min(sum(values.get(tuple(choice[i] for i in scope),default) for scope,default,values in model['functions']),model['upper'])
    assert original_cost(anchor)==1133936141479
    states=[]
    for i,domain in enumerate(model['domains']):
        alternatives=[(original_cost(anchor[:i]+[s]+anchor[i+1:]),s) for s in range(domain) if s!=anchor[i]]
        allowed=[entry for entry in alternatives if entry[0]<model['upper']]
        states.append([anchor[i],min(allowed)[1]] if allowed else [anchor[i]])
    active=[i for i,s in enumerate(states) if len(s)==2];n=len(active);position={site:i for i,site in enumerate(active)}
    constant=0;linear=[0]*n;pairs=[[0]*n for _ in range(n)]
    for scope,default,values in model['functions']:
        varying=[s for s in scope if s in position]
        def cost(bits):
            choices={site:states[site][b] for site,b in zip(varying,bits)}
            return values.get(tuple(choices.get(site,states[site][0]) for site in scope),default)
        if not varying:constant+=cost([])
        elif len(varying)==1:
            i=position[varying[0]];a,b=cost([0]),cost([1])
            constant+=a;linear[i]+=b-a
        else:
            i,j=[position[s] for s in varying]
            aa,ab,ba,bb=[cost([a,b]) for a,b in [(0,0),(0,1),(1,0),(1,1)]]
            constant+=aa;linear[i]+=ba-aa;linear[j]+=ab-aa
            pairs[min(i,j)][max(i,j)]+=bb-ba-ab+aa
    result={'source_name':model['name'],'positions':n,'active_sites':active,'states':states,'upper':model['upper'],'constant':constant,'linear':linear,'pairs':pairs,
            'selection':'Published first feasible incumbent plus lowest-energy feasible single-site alternative at each position; a position without an alternative is fixed. All original pairwise costs and forbidden semantics retained. This is a neighborhood pilot around a known solution.',
            'anchor_source':'https://web-genobioinfo.toulouse.inrae.fr/~tschiex/CPD/CPD-instances/1BK2.matrix.24p.17aa.usingEref_self_digit8.wcsp.out',
            'scope':'Restricted CPD subspace. Not the full published 1BK2 GMEC result and not a newly validated biological design.'}
    result['model_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result


def energy(restricted,identity):
    bits=[(identity>>i)&1 for i in range(restricted['positions'])]
    total=restricted['constant']+sum(a*b for a,b in zip(restricted['linear'],bits))
    total+=sum(restricted['pairs'][i][j]*bits[i]*bits[j] for i in range(len(bits)) for j in range(i+1,len(bits)))
    return min(total,restricted['upper'])


def direct_energy(model,restricted,identity):
    choice=[states[0] for states in restricted['states']]
    for i,site in enumerate(restricted['active_sites']):choice[site]=restricted['states'][site][(identity>>i)&1]
    return min(sum(values.get(tuple(choice[i] for i in scope),default) for scope,default,values in model['functions']),model['upper'])


def search(restricted,n,start):
    if not 1<=n<=2**restricted['positions']:raise ValueError('Invalid count')
    if not 0<=start<2**restricted['positions']:raise ValueError('Invalid start')
    result=min((energy(restricted,(start+65537*i)%(2**restricted['positions'])),i) for i in range(n))
    return result
