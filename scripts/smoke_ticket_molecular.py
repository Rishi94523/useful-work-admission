"""Actual 256k Vina work -> ticket commitment -> selected real replay -> credit.

One honest four-unit bundle and one trace-hash-corrupted bundle. Separate new
seeded work and private output directories; no campaign or driver is modified.
"""
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import run_published_matched as M
from research.ticket_admission import TicketAdmission,encoded
from research.trace_commitment import payload,verify
from benchmark_ticket_admission import persist


def main():
    out=ROOT/'local-research/ticket-molecular-2026-09-24';out.mkdir(exist_ok=False)
    targets=json.loads((ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json').read_text())['targets']
    t=next(x for x in targets if x['target']=='wee1');lig=t['ligands'][0]
    M.EXE=ROOT/'tmp/vina-published/vina_published_tasks_v2.exe'
    spec=dict(campaign='isolated-ticket-smoke',receptor=t['receptor_sha256'],ligand=lig['sha256'],
              center=t['center'],size=t['size'],max_evals=256000,driver=M.digest(M.EXE))
    c=TicketAdmission(out/'ledger.sqlite',secrets.token_bytes(32),spec)
    (out/'manifest.json').write_text(json.dumps(spec,indent=2)+'\n')
    work=out/'work';work.mkdir();worker=M.Worker(t,lig,work)
    rows=[]
    def compute(seed,folder):
        folder.mkdir();begin=time.perf_counter()
        worker.run(1,0,seed,1,256000,folder,folder/'unused.pdbqt')
        return (folder/'0.task').read_bytes(),(folder/'0.task.trace').read_bytes(),(time.perf_counter()-begin)*1000
    try:
        for kind in ('honest','corrupted'):
            ticket=c.issue(kind);items={};client_ms=0
            for seed in ticket['assignment']['seeds']:
                pool,trace,ms=compute(seed,work/(kind+'_'+str(seed)));client_ms+=ms
                v=json.loads(payload(pool,trace))
                if kind=='corrupted':v['trace_sha256']='0'*64
                items[str(seed)]=encoded(v).decode()
            body=encoded(items);root=hashlib.sha256(body).hexdigest()
            submitted=c.submit(ticket['ticket'],root,body,kind);assert submitted['status']=='queued'
            row=c.pending('new');assert row['id']==submitted['id'];selected=json.loads(row['draws'])[0]
            pool,trace,ms=compute(selected,work/(kind+'_replay'))
            good=verify(items[str(selected)].encode(),pool,trace)
            c.finish(row['id'],(root,good),persist)
            if good:c.redeem(row['id'],kind)
            assert good==(kind=='honest')
            rows.append(dict(kind=kind,units=4,client_ms=client_ms,replay_ms=ms,
                             payload_bytes=len(body),audit_passed=good,credit_redeemed=good))
            print(json.dumps(rows[-1]),flush=True)
    finally:worker.close()
    (out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')


if __name__=='__main__':main()
