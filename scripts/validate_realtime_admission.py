"""Amendment 17: bounded FIFO ticket queue with real HTTP and native replay.

Isolated ledgers, previously computed honest credits, wall-clock arrivals.
Not the effort-priority simulator or a production deployment benchmark.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import run_published_matched as M
from research.ticket_admission import TicketAdmission, encoded, solve
from research.trace_commitment import payload, verify
from benchmark_ticket_admission import persist

OUT=ROOT/'local-research/realtime-admission-2026-09-29'
WORK=ROOT/'tmp/realtime-admission-2026-09-29'
PROTOCOL_COMMIT='a2d2af1'


def resources(pid):
    """Windows process CPU and working-set readings, without installing agents."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    class Times(ctypes.Structure): _fields_=[('low',wintypes.DWORD),('high',wintypes.DWORD)]
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in
          ('peak_ws','ws','peak_pool','pool','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return None
    try:
        ts=[Times() for _ in range(4)]
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(Times)]*4
        if not kernel.GetProcessTimes(handle,*map(ctypes.byref,ts)):raise ctypes.WinError(ctypes.get_last_error())
        mem=Memory();mem.cb=ctypes.sizeof(mem)
        psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(mem),mem.cb):raise ctypes.WinError(ctypes.get_last_error())
        return dict(cpu_s=sum((t.high<<32)+t.low for t in ts[2:])/1e7,rss=mem.ws,peak_rss=mem.peak_ws)
    finally:kernel.CloseHandle(handle)


def compute(worker,seed,folder):
    folder.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter(); worker.run(1,0,seed,1,256000,folder,folder/'unused.pdbqt')
    return payload((folder/'0.task').read_bytes(),(folder/'0.task.trace').read_bytes()).decode(),time.perf_counter()-start


def run_case(mode,rep,factor,R,target,ligand,fixtures,template):
    name=f'{mode}-{rep}-{factor:g}';folder=WORK/name;folder.mkdir()
    c=TicketAdmission(folder/'ledger.sqlite',secrets.token_bytes(32),dict(campaign='realtime-validation',driver=M.digest(M.EXE),
        receptor=target['receptor_sha256'],ligand=ligand['sha256'],budget=256000),ttl=3600,issuance_rate=1000)
    rows=[];events=[];errors=[];lock=threading.Lock();stopping=threading.Event()
    start=0.;deadline=0.;queue_peak=0;byte_peak=0
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            try:
                n=int(self.headers.get('Content-Length','-1'))
                if not 0<=n<=900000:self.send_error(413);return
                d=json.loads(self.rfile.read(n));owner=self.headers['X-Test-Session']
                if self.path=='/offer':r=c.offer(d['ticket'],d['root'],owner)
                elif self.path=='/submit':r=c.submit(d['ticket'],d['root'],base64.b64decode(d['body'],validate=True),owner,d.get('proof'))
                else:raise ValueError('Path')
                data=encoded(r);self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except Exception as e:
                with lock: errors.append('http:'+type(e).__name__+':'+str(e))
                self.send_error(400)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    ht=threading.Thread(target=http.serve_forever,daemon=True);ht.start()
    def call(path,owner,data):
        req=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/{path}',data=encoded(data),
            headers={'Content-Type':'application/json','X-Test-Session':owner})
        with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
    # Issue all tickets and compute required honest work before the measured window.
    arrivals=[]
    for kind,rate in [('new',R/4),('trusted',R/4),('attack',factor*R)]:
        if not rate:continue
        i=0
        while i/rate<12:
            arrivals.append(dict(kind=kind,at=i/rate,owner=f'{kind}-{i}'));i+=1
    arrivals.sort(key=lambda a:(a['at'],a['kind']))
    prep_begin=time.perf_counter();newly_computed=0
    for a in arrivals:
        t=c.issue(a['owner'],trusted=a['kind']=='trusted')
        while t['status']=='rate_limited':
            time.sleep(.005);t=c.issue(a['owner'],trusted=a['kind']=='trusted')
        assert t['status']=='ticket',t
        a['ticket']=t['ticket'];a['id']=t['assignment']['id'];items={}
        for seed in t['assignment']['seeds']:
            if a['kind']=='attack':
                fake=json.loads(template);fake['trace_sha256']='0'*64;items[str(seed)]=encoded(fake).decode()
            else:
                if seed not in fixtures:
                    fixtures[seed],_=compute(prep_worker,seed,WORK/'fixtures'/str(seed));newly_computed+=1
                items[str(seed)]=fixtures[seed]
        # Control work is also performed before submission; its check is real.
        if mode in ('pow','replay'):
            challenge='pow-control:'+t['ticket'];proof=solve(challenge,16)
            body=encoded(dict(items=items,gate_proof=proof))
            # Keep TicketAdmission's scientific-unit mapping unchanged. Encode
            # the proof in each value; same control proof checked once per request.
            items={s:encoded(dict(unit=v,gate_proof=proof)).decode() for s,v in items.items()}
        a['body']=encoded(items);a['root']=hashlib.sha256(a['body']).hexdigest()
    prep_s=time.perf_counter()-prep_begin
    workers={}
    if mode=='replay':
        for tier in ('new','trusted'):
            wd=folder/tier;wd.mkdir();workers[tier]=M.Worker(target,ligand,wd)
    def consume(tier):
        serial=0
        while not stopping.is_set():
            row=c.pending(tier)
            if not row:time.sleep(.005);continue
            began=time.perf_counter();cpu0=resources(workers[tier].p.pid)['cpu_s'] if mode=='replay' else 0
            try:
                selected=json.loads(row['draws'])[0];items=json.loads(row['payload'])
                if mode=='replay':
                    w=workers[tier];d=folder/tier/str(serial);d.mkdir();serial+=1
                    w.run(1,0,selected,1,256000,d,d/'unused.pdbqt')
                    good=verify(json.loads(items[str(selected)])['unit'].encode(),(d/'0.task').read_bytes(),(d/'0.task.trace').read_bytes())
                else:
                    p=json.loads(items[str(selected)])['gate_proof']
                    expected='pow-control:'+row['ticket']
                    good=(p['challenge']==expected and type(p['nonce'])==int and 0<=p['nonce']<2**64 and
                        int.from_bytes(hashlib.sha256(expected.encode()+p['nonce'].to_bytes(8,'big')).digest(),'big')<2**240)
                c.finish(row['id'],(row['root'],good),persist)
                if good:c.redeem(row['id'],row['owner'])
                done=time.perf_counter()
                with lock:events.append(dict(id=row['id'],owner=row['owner'],tier=tier,accepted=good,
                    completed=done-start,service_s=done-began,queue_and_service_s=time.time()-row['issued'],
                    native_cpu_s=resources(workers[tier].p.pid)['cpu_s']-cpu0 if mode=='replay' else 0,
                    units=len(items)))
            except Exception as e:
                with lock:errors.append('replay:'+type(e).__name__+':'+str(e))
                stopping.set()
    def visitor(a):
        due=start+a['at'];remaining=due-time.perf_counter()
        if remaining>0:time.sleep(remaining)
        begin=time.perf_counter();proof=None;puzzle_s=0.;hashes=0
        r={'status':'error'}
        try:
            offer=call('offer',a['owner'],dict(ticket=a['ticket'],root=a['root']))
            for attempt_index in range(2):
                if offer['status']=='puzzle':
                    b=time.perf_counter();proof=solve(offer['challenge'],offer['bits']);puzzle_s+=time.perf_counter()-b;hashes+=proof['nonce']+1
                r=call('submit',a['owner'],dict(ticket=a['ticket'],root=a['root'],body=base64.b64encode(a['body']).decode(),proof=proof))
                if r['status']!='puzzle_required':break
                offer=call('offer',a['owner'],dict(ticket=a['ticket'],root=a['root']))
        except Exception as e:
            with lock:errors.append('client:'+type(e).__name__+':'+str(e))
        with lock:rows.append(dict(id=a['id'],kind=a['kind'],scheduled=a['at'],began=begin-start,
            lag_s=begin-due,response_s=time.perf_counter()-begin,response=r,puzzle_s=puzzle_s,puzzle_hashes=hashes,bytes=len(a['body'])))
    initial=resources(os.getpid());native_initial={k:resources(w.p.pid) for k,w in workers.items()}
    start=time.perf_counter();deadline=start+20
    threads=[threading.Thread(target=consume,args=(tier,),daemon=True) for tier in ('new','trusted')]
    for t in threads:t.start()
    # Independent honest submissions; one sequential attacker producer.
    def attacker():
        for a in arrivals:
            if a['kind']=='attack':visitor(a)
    at=threading.Thread(target=attacker,daemon=True);at.start()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(visitor,a) for a in arrivals if a['kind']!='attack']
        while time.perf_counter()<deadline and not stopping.is_set():
            with c.db() as db:
                n,b=db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM queue WHERE state='QUEUED'").fetchone()
            queue_peak=max(queue_peak,n);byte_peak=max(byte_peak,b)
            time.sleep(.05)
        at.join(timeout=20)
        for f in futures:f.result()
    stopping.set()
    for t in threads:t.join(timeout=30)
    ending=resources(os.getpid());native_final={k:resources(w.p.pid) for k,w in workers.items()}
    for w in workers.values():w.close()
    http.shutdown();http.server_close();ht.join()
    by={r['id']:r for r in rows};summary={}
    for kind in ('new','trusted','attack'):
        rs=[r for r in rows if r['kind']==kind];ev=[e for e in events if by[e['id']]['kind']==kind]
        successes=[e for e in ev if e['accepted'] and e['completed']-by[e['id']]['began']<=5 and e['completed']<=20]
        summary[kind]=dict(offered=len(rs),queued=sum(r['response']['status']=='queued' for r in rs),
            accepted=sum(e['accepted'] and e['completed']<=20 for e in ev),deadline_success=len(successes),
            deadline_fraction=len(successes)/len(rs) if rs else None,
            response_counts={k:sum(r['response']['status']==k for r in rs) for k in sorted({r['response']['status'] for r in rs})},
            max_schedule_lag_s=max((r['lag_s'] for r in rs),default=0),
            realized_arrivals_per_s=sum(r['began']<12 for r in rs)/12,
            accepted_latency_s=[e['completed']-by[e['id']]['began'] for e in ev if e['accepted']],
            paid_entry_hashes=sum(r['puzzle_hashes'] for r in rs),paid_entry_wall_s=sum(r['puzzle_s'] for r in rs))
    result=dict(mode=mode,rep=rep,attack_factor=factor,R=R,summary=summary,errors=errors,
        queue_peak=queue_peak,queued_payload_peak=byte_peak,upload_bytes=sum(r['bytes'] for r in rows),
        honest_preparation_s=prep_s,new_fixture_units=newly_computed,
        native_cpu_s={k:native_final[k]['cpu_s']-v['cpu_s'] for k,v in native_initial.items()},
        native_peak_rss={k:v['peak_rss'] for k,v in native_final.items()},
        harness_cpu_s=ending['cpu_s']-initial['cpu_s'],harness_peak_rss=ending['peak_rss'],
        scientific_units_persisted=sum(e['units'] for e in events if e['accepted']) if mode=='replay' else 0,
        rows=rows,events=events)
    (OUT/(name+'.json')).write_text(json.dumps(result,indent=2));print(name,json.dumps(summary),flush=True)
    return result


def main():
    global prep_worker
    OUT.mkdir(exist_ok=False);WORK.mkdir(exist_ok=False)
    targets=json.loads((ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json').read_text())['targets']
    target=next(t for t in targets if t['target']=='wee1');ligand=target['ligands'][0]
    M.EXE=ROOT/'tmp/vina-published/vina_published_tasks_v2.exe'
    wd=WORK/'prepare';wd.mkdir();prep_worker=M.Worker(target,ligand,wd)
    manifest=dict(protocol_commit=PROTOCOL_COMMIT,driver_sha256=M.digest(M.EXE),runner_sha256=M.digest(Path(__file__)),
        prototype_sha256=M.digest(ROOT/'research/ticket_admission.py'),inputs_sha256=M.digest(ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json'),
        limitations='Real loopback HTTP and replay; single laptop, FIFO reservations, precomputed fixture credits, submission latency, not end-to-end browser or priority-queue validation. Harness CPU includes clients and server. Fresh ledger for every case; fixtures reused across independent replications.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    fixtures={};times=[]
    try:
        for seed in range(4):
            fixtures[seed],s=compute(prep_worker,seed,WORK/'fixtures'/str(seed));times.append(s)
        R=1/statistics.median(times)
        (OUT/'calibration.json').write_text(json.dumps(dict(seconds=times,R=R),indent=2))
        print('calibrated R',R,flush=True)
        results=[]
        for rep in range(3):
            for factor in (0,.75,2):
                for mode in (('replay','pow') if rep%2==0 else ('pow','replay')):
                    results.append(run_case(mode,rep,factor,R,target,ligand,fixtures,fixtures[0]))
        def pooled(mode,kind):
            rs=[r['summary'][kind] for r in results if r['mode']==mode and r['attack_factor']==2]
            return sum(r['deadline_success'] for r in rs)/sum(r['offered'] for r in rs)
        summary=dict(R=R,cases=len(results),errors=sum(len(r['errors']) for r in results),
            RT1=all((e['accepted']==(e['owner'].split('-')[0]!='attack')) for r in results if r['mode']=='replay' for e in r['events']),
            RT2=pooled('replay','new')<pooled('pow','new'),
            RT3=all(pooled(mode,'trusted')>=.9 for mode in ('replay','pow')),
            high_load_deadline_fraction={mode:{kind:pooled(mode,kind) for kind in ('new','trusted')} for mode in ('replay','pow')})
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    finally:prep_worker.close()


if __name__=='__main__':main()
