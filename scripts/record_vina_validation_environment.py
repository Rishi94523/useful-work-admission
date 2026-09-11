"""Record non-sensitive hardware/runtime context for the local measurements."""
import ctypes,hashlib,json,os,platform,subprocess,winreg
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Memory(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ['total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','extended_virtual']]
m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:cpu=winreg.QueryValueEx(k,'ProcessorNameString')[0].strip()
files=['scripts/build_vina_resource_probe.py','scripts/benchmark_vina_resources.mjs','scripts/validate_vina_stock_controls.py','scripts/benchmark_vina_validated_multitarget.py','scripts/benchmark_vina_tutorial.py','scripts/benchmark_vina_matched_ranking.py']
result={'platform':platform.platform(),'processor':cpu,'logical_processors':os.cpu_count(),'physical_ram_bytes':m.total_physical,'node':subprocess.check_output(['node','--version'],text=True).strip(),'python':platform.python_version(),'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],'reference_commit':'3b564dd2496bd21e743591e55efaa3daf1c154ae','scripts_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'timing_scope':'Local research measurements. Some experiments run concurrently. No phone or participant results, no isolated speedup claim.'}
(ROOT/'docs/evaluation/vina_validation_2026-09-10/environment.json').write_text(json.dumps(result,indent=2)+'\n');print(cpu,round(m.total_physical/2**30,1),'GiB')
