"""Sample only explicit benchmark Chrome PIDs; OS lifetime peaks survive sampling gaps."""
import ctypes,json,sys,threading,time
from ctypes import wintypes as w
from pathlib import Path
class Counters(ctypes.Structure):
 _fields_=[('cb',w.DWORD),('PageFaultCount',w.DWORD)]+[(x,ctypes.c_size_t) for x in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage']]
kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
kernel.CloseHandle.argtypes=[w.HANDLE];psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD]
stop=threading.Event();threading.Thread(target=lambda:(sys.stdin.readline(),stop.set()),daemon=True).start()
pidfile=Path(sys.argv[1]);outfile=Path(sys.argv[2]);rows=[];peaks={};errors=set()
while not stop.is_set():
 try:pids=json.loads(pidfile.read_text())
 except (OSError,ValueError):pids=[]
 snapshot=[]
 for p in pids:
  handle=kernel.OpenProcess(0x1000|0x10,False,p['id'])
  if not handle:errors.add(p['id']);continue
  c=Counters();c.cb=ctypes.sizeof(c)
  if psapi.GetProcessMemoryInfo(handle,ctypes.byref(c),c.cb):
   r={'pid':p['id'],'type':p['type'],'working_set':c.WorkingSetSize,'os_peak_working_set':c.PeakWorkingSetSize,'private_commit':c.PrivateUsage,'os_peak_commit':c.PeakPagefileUsage};snapshot.append(r)
   old=peaks.setdefault(str(p['id']),r.copy())
   for key in ['working_set','os_peak_working_set','private_commit','os_peak_commit']:old[key]=max(old[key],r[key])
  else:errors.add(p['id'])
  kernel.CloseHandle(handle)
 rows.append({'time':time.time(),'processes':snapshot});stop.wait(.025)
outfile.write_text(json.dumps({'scope':'Windows GetProcessMemoryInfo. Per-process OS lifetime peak working set; 25ms requested sampling. Tree sums double-count shared pages and are not unique physical RAM. PrivateUsage is committed private memory, not private resident memory.','peaks':peaks,'errors':sorted(errors),'samples':rows},indent=2)+'\n')
