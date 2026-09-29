"""Standard-library Windows benchmark for amendment 19b. No network access.

Run only from a reviewed package created by build_portable_dense_benchmark.py.
Benchmark keys are public fixtures, not production verifier secrets.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import sys
import time
import winreg


def digest(data): return hashlib.sha256(data).hexdigest()


def check_manifest(root):
    m=json.loads((root/'manifest.json').read_text())
    for name,expected in m['files'].items():
        p=(root/name).resolve()
        if not p.is_relative_to(root.resolve()):raise ValueError('Invalid package path')
        if digest(p.read_bytes())!=expected:raise ValueError('Package checksum failed: '+name)
    return m


def power():
    class Status(C.Structure):
        _fields_=[('ac',C.c_byte),('flags',C.c_byte),('battery_percent',C.c_byte),('saver',C.c_byte),('remaining',C.c_uint32),('full',C.c_uint32)]
    s=Status();ok=C.windll.kernel32.GetSystemPowerStatus(C.byref(s))
    return dict(ac=int(s.ac),battery_percent=int(s.battery_percent),saver=int(s.saver)) if ok else None


class Network:
    def __init__(self,root,meta,lib):
        self.meta=meta;self.layers=len(meta['dims'])-1;self.dims=(C.c_int32*len(meta['dims']))(*meta['dims'])
        self.width=sum(meta['dims'][1:]);self.input_width=meta['dims'][0]
        self.buffers={}
        for key in ('w','bias','s','r','rb','bounds','mult','inputs'):
            b=(root/meta['name']/(key+'.bin')).read_bytes()
            self.buffers[key]=C.create_string_buffer(b)
        self.lib=lib
        self.forward_fn=lib.dense_forward
        self.forward_fn.argtypes=[C.c_int]+[C.c_void_p]*7+[C.c_size_t]
        self.forward_fn.restype=C.c_int
        self.verify_fn=lib.dense_verify
        self.verify_fn.argtypes=[C.c_int]+[C.c_void_p]*9+[C.c_size_t]
        self.verify_fn.restype=C.c_int

    def forward(self,x,batch,claimed=None):
        b=self.buffers
        out=C.create_string_buffer(batch*self.width*4) if claimed is None else None
        good=self.forward_fn(self.layers,self.dims,b['w'],b['bias'],b['mult'],x,out,claimed,batch)
        if claimed is not None:return bool(good)
        if not good:raise ValueError('Native forward failed')
        return out.raw

    def verify(self,x,blob,batch,audit=False):
        if len(blob)!=batch*self.width*4:return False
        digest(blob)
        tr=C.create_string_buffer(blob);logits=C.create_string_buffer(batch*self.meta['dims'][-1]*4);b=self.buffers
        good=self.verify_fn(self.layers,self.dims,b['s'],b['r'],b['rb'],b['bounds'],b['mult'],x,tr,logits,batch)
        if not good:return False
        return self.forward(x,batch,tr) if audit else True

    def select(self,indices):
        raw=self.buffers['inputs'].raw
        return C.create_string_buffer(b''.join(raw[i*self.input_width:(i+1)*self.input_width] for i in indices))


def measure(root,meta,lib,session):
    begin=time.perf_counter();net=Network(root,meta,lib);load_ms=(time.perf_counter()-begin)*1000
    for i,expected in enumerate(meta['trace_hashes']):
        assert digest(net.forward(net.select([i]),1))==expected,'Reference trace mismatch'
    rng=random.Random(20260929+session);result=[]
    for batch in (1,32):
        samples=[];tested=rejected=0
        for rep in range(12+64):
            indices=rng.sample(range(128),batch);x=net.select(indices);blob=net.forward(x,batch)
            if rep==12:
                offset=0
                for width in meta['dims'][1:]:
                    pos=rng.randrange(batch)*net.width+offset+rng.randrange(width)
                    value=struct.unpack_from('<i',blob,pos*4)[0]
                    for delta in (1,-1,2**31-1):
                        changed=bytearray(blob);shifted=(value+delta+2**31)%2**32-2**31
                        struct.pack_into('<i',changed,pos*4,shifted)
                        rejected+=not net.verify(x,bytes(changed),batch);tested+=1
                    offset+=width
            methods=['forward','verify','audit'];rng.shuffle(methods);times={}
            for kind in methods:
                b=time.perf_counter_ns()
                v=net.forward(x,batch) if kind=='forward' else net.verify(x,blob,batch,kind=='audit')
                times[kind]=(time.perf_counter_ns()-b)/1e6
                assert v==blob if kind=='forward' else v,kind+' failed'
            if rep>=12:samples.append(times)
        med={k:statistics.median(s[k] for s in samples) for k in samples[0]}
        rows={str(p):med['forward']/((1-p)*med['verify']+p*med['audit']) for p in (0,.02,.08,.25,1)}
        result.append(dict(model=meta['name'],batch=batch,session=session,load_ms=load_ms,median_ms=med,
            native_reference_leverage=rows,tested_perturbations=tested,rejected=rejected,samples=samples,
            reference_traces_verified=len(meta['trace_hashes'])))
        print(meta['name'],'batch',batch,'session',session,'L8',round(rows['0.08'],3),flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='result.json');args=ap.parse_args()
    root=Path(__file__).resolve().parent;out=Path(args.output).resolve()
    if out.exists():raise SystemExit('Output exists; rename it before repeating the experiment.')
    if sys.platform!='win32' or C.sizeof(C.c_void_p)!=8:raise SystemExit('64-bit Windows Python is required.')
    manifest=check_manifest(root)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
        cpu=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    # No machine name, user name, filesystem path or IP address is recorded.
    result=dict(protocol='19b',package_sha256=digest((root/'manifest.json').read_bytes()),cpu=cpu,
        logical_cpus=os.cpu_count(),os=platform.system()+' '+platform.release(),python=platform.python_version(),
        power_before=power(),rows=[],limitations=manifest['limitations'])
    lib=C.CDLL(str(root/'dense_check.dll'))
    for session in range(3):
        for meta in manifest['models']:result['rows'].extend(measure(root,meta,lib,session))
        out.write_text(json.dumps(result,indent=2))
    result['power_after']=power();result['PH1']=all(r['tested_perturbations']==r['rejected'] for r in result['rows'])
    out.write_text(json.dumps(result,indent=2));print('Finished. Return the result JSON file. No uploads were made.')


if __name__=='__main__':main()
