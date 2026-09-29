using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// HARNESS ONLY. Never executes or claims the Rust candidate guard.
class SourceFixtureSynthetic {
    [StructLayout(LayoutKind.Sequential)] struct SI { public int cb; public IntPtr reserved,desktop,title; public int x,y,xs,ys,xc,yc,fill,flags; public short show,cbres; public IntPtr res,stdin,stdout,stderr; }
    [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr process,thread; public int pid,tid; }
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SI si,out PI pi);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool inside);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long created,out long exited,out long kernel,out long user);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern int GetCurrentProcessId();
    [DllImport("kernel32.dll")] static extern void SetLastError(uint error);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr process,uint ms);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool DebugSetProcessKillOnExit(bool enabled);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool WaitForDebugEvent(IntPtr debugEvent,uint ms);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool ContinueDebugEvent(int pid,int tid,uint status);
    static JavaScriptSerializer Json=new JavaScriptSerializer();
    static string Root,Exe=Assembly.GetExecutingAssembly().Location;
    static void Check(bool ok,string name) { if(!ok) throw new Exception(name+" win32="+Marshal.GetLastWin32Error()); }
    static long Created(IntPtr handle) { long a,b,c,d; Check(GetProcessTimes(handle,out a,out b,out c,out d),"GetProcessTimes"); return a; }
    static Dictionary<string,object> Identity(IntPtr handle,int pid) {
        bool member; SetLastError(0); bool ok=IsProcessInJob(handle,IntPtr.Zero,out member); int error=Marshal.GetLastWin32Error(); Check(ok,"IsProcessInJob"); Check(!member,"NoJob");
        return new Dictionary<string,object>{{"pid",pid},{"created",Created(handle)},{"queryReturn",ok?1:0},{"lastError",error},{"inJob",member}};
    }
    static void Write(string name,object value) { string path=Path.Combine(Root,name); File.WriteAllText(path+".tmp",Json.Serialize(value)); File.Move(path+".tmp",path); }
    static void Await(string name) { DateTime end=DateTime.UtcNow.AddSeconds(20); while(!File.Exists(Path.Combine(Root,name))&&DateTime.UtcNow<end) Thread.Sleep(10); Check(File.Exists(Path.Combine(Root,name)),"Await "+name); }
    static void Cleanup(ref PI child) {
        if(child.process==IntPtr.Zero) return;
        if(WaitForSingleObject(child.process,0)==258) Check(TerminateProcess(child.process,94),"TerminateOriginalChild");
        IntPtr buffer=Marshal.AllocHGlobal(176);
        try {
            DateTime end=DateTime.UtcNow.AddSeconds(10);
            while(WaitForSingleObject(child.process,0)==258&&DateTime.UtcNow<end) {
                if(!WaitForDebugEvent(buffer,100)) { Check(Marshal.GetLastWin32Error()==121,"WaitForDebugEvent"); continue; }
                int code=Marshal.ReadInt32(buffer,0),pid=Marshal.ReadInt32(buffer,4),tid=Marshal.ReadInt32(buffer,8);
                Check(pid==child.pid,"UnrelatedDebugEvent");
                if(code==3||code==6) { IntPtr file=Marshal.ReadIntPtr(buffer,16); if(file!=IntPtr.Zero) Check(CloseHandle(file),"CloseDebugImage"); }
                uint status=code==1&&unchecked((uint)Marshal.ReadInt32(buffer,16))!=0x80000003?0x80010001u:0x10002u;
                Check(ContinueDebugEvent(pid,tid,status),"ContinueDebugEvent");
            }
            Check(WaitForSingleObject(child.process,0)==0,"ReapOriginalChild");
        } finally { Marshal.FreeHGlobal(buffer); }
        Check(CloseHandle(child.thread),"CloseOriginalThread"); child.thread=IntPtr.Zero;
        Check(CloseHandle(child.process),"CloseOriginalChild"); child.process=IntPtr.Zero;
    }
    static int Main(string[] args) {
        Root=Environment.GetEnvironmentVariable("CODEX_TEST_NATIVE_DIR");
        PI child=new PI();
        try {
            object binding=Json.DeserializeObject(File.ReadAllText(Path.Combine(Root,"binding.json")));
            var worker=Identity(GetCurrentProcess(),GetCurrentProcessId());
            SI si=new SI(); si.cb=Marshal.SizeOf(typeof(SI));
            Check(CreateProcessW(Exe,new StringBuilder("\""+Exe+"\""),IntPtr.Zero,IntPtr.Zero,false,0x0100000e,IntPtr.Zero,Root,ref si,out child),"SpawnDebugOwnedSuspendedChild");
            var identity=Identity(child.process,child.pid);
            string fault=Environment.GetEnvironmentVariable("CODEX_TEST_NATIVE_FAULT");
            if(fault=="crash-before-debug-check") {
                Write("fault-child.json",identity); Await("fault-observer-ack.json"); Environment.Exit(91);
            }
            Check(DebugSetProcessKillOnExit(true),"DebugSetProcessKillOnExit");
            if(fault=="registration-failure") throw new Exception("Synthetic registration failure");
            if(fault=="crash-before-registration") {
                Write("fault-child.json",identity); Await("fault-observer-ack.json"); Environment.Exit(91);
            }
            if(fault=="crash-during-registration") {
                Write("fault-child.json",identity); Await("fault-observer-ack.json");
            }
            Write("registration.json",new Dictionary<string,object>{{"binding",binding},{"worker",worker},{"child",identity},{"sourceHandle",child.process.ToInt64()}});
            if(fault=="crash-during-registration") Environment.Exit(91);
            Await("registration-ack.json");
            if(fault=="crash-after-registration") Environment.Exit(91);
            if(fault=="timeout") Thread.Sleep(60000);
            Cleanup(ref child);
            Write("worker-receipt.json",new Dictionary<string,object>{{"binding",binding},{"binaryBlake3",new string('0',64)},
                {"worker",worker},{"child",identity},{"guard","SYNTHETIC_ACCEPTED"},{"debugKillOnExitReturn",1},{"testResult","PASSED"},
                {"cleanup",new Dictionary<string,object>{{"killed",true},{"reaped",true},{"originalChildHandleClosed",true},{"debugImageHandlesClosed",true}}}});
            return 0;
        } catch(Exception ex) { File.WriteAllText(Path.Combine(Root,"worker-error.txt"),ex.ToString()); return 1; }
        finally { Cleanup(ref child); }
    }
}
