"""Read-only ambient Job queries and original-handle disposable launch diagnostics."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import subprocess
import sys

k=c.WinDLL('kernel32',use_last_error=True)
def api(name,args,result=w.BOOL):
    f=getattr(k,name);f.argtypes=args;f.restype=result;return f
class Basic(c.Structure):
    _fields_=[('processTime',c.c_int64),('jobTime',c.c_int64),('flags',w.DWORD),('min',c.c_size_t),('max',c.c_size_t),('active',w.DWORD),('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class Io(c.Structure):
    _fields_=[(name,c.c_uint64) for name in ['readOp','writeOp','otherOp','readBytes','writeBytes','otherBytes']]
class Limits(c.Structure):
    _fields_=[('basic',Basic),('io',Io),('processMemory',c.c_size_t),('jobMemory',c.c_size_t),('peakProcess',c.c_size_t),('peakJob',c.c_size_t)]
class Startup(c.Structure):
    _fields_=[('cb',w.DWORD),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR)]+[(name,w.DWORD) for name in ['x','y','xs','ys','xc','yc','fill','flags']]+[('show',w.WORD),('cbres',w.WORD),('res',w.LPVOID),('stdin',w.HANDLE),('stdout',w.HANDLE),('stderr',w.HANDLE)]
class Process(c.Structure):
    _fields_=[('process',w.HANDLE),('thread',w.HANDLE),('pid',w.DWORD),('tid',w.DWORD)]
current=api('GetCurrentProcess',[],w.HANDLE)
membership=api('IsProcessInJob',[w.HANDLE,w.HANDLE,c.POINTER(w.BOOL)])
query=api('QueryInformationJobObject',[w.HANDLE,w.DWORD,w.LPVOID,w.DWORD,c.POINTER(w.DWORD)])
create=api('CreateProcessW',[w.LPCWSTR,w.LPWSTR,w.LPVOID,w.LPVOID,w.BOOL,w.DWORD,w.LPVOID,w.LPCWSTR,c.POINTER(Startup),c.POINTER(Process)])
terminate=api('TerminateProcess',[w.HANDLE,w.UINT])
wait=api('WaitForSingleObject',[w.HANDLE,w.DWORD],w.DWORD)
close=api('CloseHandle',[w.HANDLE])
def member(handle):
    inside=w.BOOL();c.set_last_error(0);ok=membership(handle,None,c.byref(inside));return {'return':ok,'lastError':c.get_last_error(),'inJob':bool(inside.value) if ok else None}
parser=argparse.ArgumentParser();parser.add_argument('--binary',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
assert args.binary.is_file() and not args.output.exists()
limit=Limits();returned=w.DWORD();c.set_last_error(0);ok=query(None,9,c.byref(limit),c.sizeof(limit),c.byref(returned));query_error=c.get_last_error()
result={'scope':'host capability diagnosis only; no guard/fixture acceptance','python':sys.executable,'hostMembership':member(current()),'immediateJobQuery':{'return':ok,'lastError':query_error,'limitFlags':limit.basic.flags if ok else None},'launches':[]}
for flags in [0x09000004,0x08000004]:
    si=Startup();si.cb=c.sizeof(si);pi=Process();c.set_last_error(0)
    ok=create(str(args.binary),c.create_unicode_buffer(subprocess.list2cmdline([str(args.binary)])),None,None,False,flags,None,str(args.binary.parent),c.byref(si),c.byref(pi))
    record={'flags':flags,'return':ok,'lastError':c.get_last_error()}
    if ok:
        try:
            record['pid']=pi.pid;record['membership']=member(pi.process)
            c.set_last_error(0);record['terminateReturn']=terminate(pi.process,79);record['terminateError']=c.get_last_error();record['wait']=wait(pi.process,5000)
        finally:
            record['threadHandleClosed']=bool(close(pi.thread));record['processHandleClosed']=bool(close(pi.process))
    result['launches'].append(record)
args.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
assert all(not row['return'] or (row['terminateReturn'] and row['wait']==0 and row['threadHandleClosed'] and row['processHandleClosed']) for row in result['launches'])
