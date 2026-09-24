"""Loopback HTTP mixed-traffic exercise of the isolated ticket prototype.

HTTP, HMAC, SHA-256 puzzles, payload checks and SQLite queue/credits are real.
Arrival time and 1.52s molecular replay service time are simulated. Scientific
verdicts use fixtures: this is NOT an end-to-end molecular throughput result.
"""
import base64
import argparse
import hashlib
import json
import secrets
import sys
import tempfile
import threading
import time
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.ticket_admission import TicketAdmission, encoded, solve


def persist(db,row):
    db.execute('CREATE TABLE IF NOT EXISTS science(id TEXT PRIMARY KEY,root TEXT,payload BLOB)')
    db.execute('INSERT INTO science VALUES(?,?,?)',(row['id'],row['root'],row['payload']))


def run(folder,attack,bits=10,issuance_rate=2):
    now=[0.];c=TicketAdmission(folder/'ledger.sqlite',secrets.token_bytes(32),
        {'campaign':'fixture','input_hashes':['fixture-only'],'max_evals':256000},clock=lambda:now[0],puzzle_bits=bits,issuance_rate=issuance_rate)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','-1'))
                if not 0<=size<=900_000: self.send_error(413);return
                # Harness session is server-authenticated for this loopback experiment.
                # Production must replace this header mapping with real authentication.
                owner=self.headers['X-Test-Session'];d=json.loads(self.rfile.read(size))
                if self.path=='/issue':r=c.issue(owner,trusted=owner.startswith('trusted-'))
                elif self.path=='/offer':r=c.offer(d['ticket'],d['root'],owner)
                elif self.path=='/submit':r=c.submit(d['ticket'],d['root'],base64.b64decode(d['body'],validate=True),owner,d.get('proof'))
                else:raise ValueError('Path')
                data=encoded(r);self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except (ValueError,KeyError,TypeError):self.send_error(400)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    counts=Counter();paid_ms=[];paid_hashes=0;waits={'new':[],'trusted':[]};active={};maxrows=maxbytes=0
    def call(path,owner,d):
        req=urllib.request.Request('http://127.0.0.1:%d/%s'%(http.server_port,path),data=encoded(d),headers={'X-Test-Session':owner,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
    def visitor(owner,kind):
        nonlocal paid_hashes
        t=call('issue',owner,{})
        if t['status']!='ticket':counts[kind+':'+t['status']]+=1;return
        counts[kind+':tickets']+=1
        if kind=='idle':return
        body=encoded({str(s):('honest' if kind=='honest' else 'fake') for s in t['assignment']['seeds']})
        root=hashlib.sha256(body).hexdigest();offer=call('offer',owner,dict(ticket=t['ticket'],root=root));proof=None
        if offer['status']=='puzzle' and kind in ('honest','paid'):
            begin=time.perf_counter();proof=solve(offer['challenge'],offer['bits']);paid_ms.append((time.perf_counter()-begin)*1000);paid_hashes+=proof['nonce']+1
            counts[kind+':puzzles']+=1
        r=call('submit',owner,dict(ticket=t['ticket'],root=root,body=base64.b64encode(body).decode(),proof=proof))
        counts[kind+':'+r['status']]+=1
    try:
        # 120 simulated seconds: 0.5/s honest newcomers + 0.5/s established,
        # 4/s fresh attacker identities. No retries; report denial explicitly.
        for tick in range(480):
            now[0]=tick*.25
            for tier in ('new','trusted'):
                if tier in active and active[tier][0]<=now[0]:
                    _,r=active.pop(tier);good=all(v=='honest' for v in json.loads(r['payload']).values())
                    c.finish(r['id'],(r['root'],good),persist)
                    counts['audits']+=1
                    if good:
                        c.redeem(r['id'],r['owner']);counts[tier+':honest_granted']+=1;waits[tier].append(now[0]-r['issued'])
                    else:counts['attacker_rejected']+=1
            if attack!='none':visitor('attacker-'+str(tick),attack)
            if tick%8==0:
                visitor('new-honest-'+str(tick),'honest');visitor('trusted-honest-'+str(tick),'honest')
            for tier in ('new','trusted'):
                if tier not in active:
                    r=c.pending(tier)
                    if r:active[tier]=(now[0]+1.52,r)
            with c.db() as db:
                n,b=db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM queue WHERE state='QUEUED'").fetchone()
                maxrows=max(maxrows,n);maxbytes=max(maxbytes,b)
        # Drain without new arrivals; bounded by ticket deadlines.
        for tick in range(480,960):
            now[0]=tick*.25
            for tier in ('new','trusted'):
                if tier in active and active[tier][0]<=now[0]:
                    _,r=active.pop(tier)
                    good=all(v=='honest' for v in json.loads(r['payload']).values())
                    try:
                        c.finish(r['id'],(r['root'],good),persist);counts['audits']+=1
                        if good:c.redeem(r['id'],r['owner']);counts[tier+':honest_granted']+=1;waits[tier].append(now[0]-r['issued'])
                        else:counts['attacker_rejected']+=1
                    except ValueError:counts['expired_while_auditing']+=1
                if tier not in active:
                    r=c.pending(tier)
                    if r:active[tier]=(now[0]+1.52,r)
            if not active:break
        def stats(xs):
            xs=sorted(xs);return {'n':len(xs),'p95_seconds':xs[min(len(xs)-1,int(.95*len(xs)))] if xs else None}
        return dict(attack=attack,counts=dict(counts),honest_arrivals_per_tier=60,
            waits={k:stats(v) for k,v in waits.items()},max_queue_rows=maxrows,max_payload_bytes=maxbytes,
            real_puzzle_solves=len(paid_ms),real_puzzle_wall_ms=sum(paid_ms),real_puzzle_hashes=paid_hashes,
            simulated_replay_cpu_seconds=counts['audits']*1.52,
            puzzle_bits=bits,issuance_rate=issuance_rate,
            limits='Serial HTTP arrivals; fixture verdicts; simulated service time. Puzzle costs measured, but arrival schedule does not enforce a client CPU budget. Queue delays exclude molecular client work and puzzle time. Not deployment calibration.')
    finally:http.shutdown();http.server_close();thread.join()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--bits',type=int,default=10);ap.add_argument('--issuance-rate',type=float,default=2);ap.add_argument('--suffix',default='');args=ap.parse_args()
    if any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.suffix):raise ValueError('Suffix')
    out=ROOT/('local-research/ticket-prototype-2026-09-24'+args.suffix);out.mkdir(exist_ok=False)
    (out/'manifest.json').write_text(json.dumps({'runner':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prototype':hashlib.sha256((ROOT/'research/ticket_admission.py').read_bytes()).hexdigest(),
        'cases':['none','idle','unpaid','paid'],'honest_per_tier_per_s':.5,'attacker_per_s':4,'duration_s':120,
        'replay_workers':2,'replay_time_s':1.52,'puzzle_bits':args.bits,'issuance_rate':args.issuance_rate,'scientific_verdict':'fixture'},indent=2))
    results=[]
    for attack in ('none','idle','unpaid','paid'):
        with tempfile.TemporaryDirectory(dir=out) as d:r=run(Path(d),attack,args.bits,args.issuance_rate)
        results.append(r);print(json.dumps(r),flush=True)
        (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':main()
