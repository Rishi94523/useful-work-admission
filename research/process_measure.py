"""Windows research subprocess timings and process-tree working-set samples.

RSS sums can double-count shared pages. These are not GPU/device-wide or private
browser-WASM peaks. Sampling can miss short-lived child processes.
"""
import ctypes
from ctypes import wintypes as W
import subprocess
import time

class Memory(ctypes.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD),*[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]]
class ProcessEntry(ctypes.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
K=ctypes.WinDLL('kernel32',use_last_error=True);P=ctypes.WinDLL('psapi',use_last_error=True)
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenProcess.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE]
K.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];K.CreateToolhelp32Snapshot.restype=W.HANDLE
K.Process32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(ProcessEntry)]
K.Process32NextW.argtypes=[W.HANDLE,ctypes.POINTER(ProcessEntry)]
P.GetProcessMemoryInfo.argtypes=[W.HANDLE,ctypes.POINTER(Memory),W.DWORD]

def descendants(pid):
    snap=K.CreateToolhelp32Snapshot(2,0)
    if snap==ctypes.c_void_p(-1).value:return {pid}
    entries=[];entry=ProcessEntry();entry.dwSize=ctypes.sizeof(entry)
    try:
        ok=K.Process32FirstW(snap,ctypes.byref(entry))
        while ok:
            entries.append((entry.th32ProcessID,entry.th32ParentProcessID))
            ok=K.Process32NextW(snap,ctypes.byref(entry))
    finally:K.CloseHandle(snap)
    ids={pid}
    while True:
        enlarged=ids|{child for child,parent in entries if parent in ids}
        if enlarged==ids:return ids
        ids=enlarged

def process_memory(pid):
    handle=K.OpenProcess(0x0410,False,pid)
    if not handle:return None
    try:
        memory=Memory();memory.cb=ctypes.sizeof(memory)
        if not P.GetProcessMemoryInfo(handle,ctypes.byref(memory),memory.cb):return None
        return memory
    finally:K.CloseHandle(handle)

def measured_run(command,log,*,timeout=1200,tree=False,private_cap=8*1024**3):
    start=time.perf_counter();peak_rss=0;peak_private=0;os_peak=0;count=0;reason=None
    with open(log,'w',encoding='utf-8') as output:
        proc=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            rss=private=0
            for pid in descendants(proc.pid) if tree else [proc.pid]:
                m=process_memory(pid)
                if m:
                    rss+=m.WorkingSetSize;private+=m.PrivateUsage
                    if pid==proc.pid:os_peak=max(os_peak,m.PeakWorkingSetSize)
            count+=1;peak_rss=max(peak_rss,rss);peak_private=max(peak_private,private)
            if time.perf_counter()-start>timeout:reason='timeout'
            if private>private_cap:reason='private_memory_cap'
            if reason:
                # Terminate the owned tree, never unrelated browser instances.
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True)
                proc.wait();break
            time.sleep(.05)
    return {'wall_seconds':time.perf_counter()-start,'exit_code':proc.returncode,'termination_reason':reason,'sampled_peak_rss_bytes':peak_rss,'sampled_peak_private_bytes':peak_private,'parent_os_peak_working_set_bytes':os_peak,'memory_samples':count,'memory_scope':'sum of process-tree RSS/private bytes, 50 ms polling; shared pages may be counted more than once' if tree else 'one process, 50 ms sampling; parent OS peak working set also sampled'}
