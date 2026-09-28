using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;

// Evidence-only process surrogate. No Codex binaries, account state or product homes.
class LifetimeFixture {
    const uint Suspended=4, Detached=8, Breakaway=0x01000000, KillOnClose=0x2000, BreakawayOk=0x800;
    const uint Query=0x1000, Terminate=1, Synchronize=0x100000, Timeout=258;
    [StructLayout(LayoutKind.Sequential)] struct SI { public int cb; public IntPtr reserved,desktop,title; public int x,y,xsize,ysize,xchars,ychars,fill,flags; public short show,cbReserved; public IntPtr reserved2,stdin,stdout,stderr; }
    [StructLayout(LayoutKind.Sequential)] struct PI { public IntPtr process,thread; public int pid,tid; }
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits { public long processTime,jobTime; public uint flags; public UIntPtr min,max; public uint active; public UIntPtr affinity; public uint priority,scheduling; }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong readOps,writeOps,otherOps,readBytes,writeBytes,otherBytes; }
    [StructLayout(LayoutKind.Sequential)] struct Limits { public BasicLimits basic; public IoCounters io; public UIntPtr processMemory,jobMemory,peakProcessMemory,peakJobMemory; }
    [DllImport("kernel32.dll",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref SI si,out PI pi);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool inside);
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attr,string name);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int cls,ref Limits info,uint length);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int cls,out Limits info,uint length,out uint returned);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint rights,bool inherit,int pid);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long created,out long exited,out long kernel,out long user);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint WaitForSingleObject(IntPtr process,uint ms);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
    static string Exe=System.Reflection.Assembly.GetExecutingAssembly().Location;
    static void Check(bool ok,string operation) { if(!ok) throw new Exception(operation+" win32="+Marshal.GetLastWin32Error()); }
    static void Log(string root,string text) { File.AppendAllText(Path.Combine(root,"events.txt"),DateTime.UtcNow.ToString("o")+" "+text+Environment.NewLine); }
    static bool Inside(IntPtr process,IntPtr job) { bool value; Check(IsProcessInJob(process,job,out value),"IsProcessInJob"); return value; }
    static long Identity(IntPtr process) { long a,b,c,d; Check(GetProcessTimes(process,out a,out b,out c,out d),"GetProcessTimes"); return a; }
    static PI Spawn(string mode,string root,uint flags) { SI si=new SI(); si.cb=Marshal.SizeOf(typeof(SI)); PI pi;
        Check(CreateProcessW(Exe,new StringBuilder("\""+Exe+"\" "+mode+" \""+root+"\""),IntPtr.Zero,IntPtr.Zero,false,flags,IntPtr.Zero,root,ref si,out pi),"CreateProcessW "+mode);
        return pi;
    }
    static void Resume(ref PI pi) { Check(ResumeThread(pi.thread)!=0xffffffff,"ResumeThread"); Check(CloseHandle(pi.thread),"CloseThread"); pi.thread=IntPtr.Zero; }
    static void Reap(ref PI pi) { if(pi.thread!=IntPtr.Zero) { CloseHandle(pi.thread); pi.thread=IntPtr.Zero; } if(pi.process!=IntPtr.Zero) { if(WaitForSingleObject(pi.process,0)==Timeout) Check(TerminateProcess(pi.process,77),"TerminateOwnedProcess"); Check(WaitForSingleObject(pi.process,5000)==0,"ReapOwnedProcess"); CloseHandle(pi.process); pi.process=IntPtr.Zero; } }
    static IntPtr Job(uint flags) { IntPtr job=CreateJobObjectW(IntPtr.Zero,null); Check(job!=IntPtr.Zero,"CreateJob"); Limits info=new Limits(); info.basic.flags=flags;
        Check(SetInformationJobObject(job,9,ref info,(uint)Marshal.SizeOf(typeof(Limits))),"SetJobLimits"); uint returned; Limits actual;
        Check(QueryInformationJobObject(job,9,out actual,(uint)Marshal.SizeOf(typeof(Limits)),out returned),"QueryJobLimits"); Check(actual.basic.flags==flags,"JobFlagMismatch"); return job;
    }
    static void AwaitFile(string path,int seconds) { DateTime end=DateTime.UtcNow.AddSeconds(seconds); while(!File.Exists(path)&&DateTime.UtcNow<end) Thread.Sleep(20); if(!File.Exists(path)) throw new Exception("Timeout "+path); }
    static void Case(string root,string name,uint? outerFlags) {
        string folder=Path.Combine(root,name); Directory.CreateDirectory(folder); IntPtr outer=IntPtr.Zero,inner=IntPtr.Zero,daemon=IntPtr.Zero; PI launcher=new PI();
        try {
            if(outerFlags.HasValue) outer=Job(outerFlags.Value); inner=Job(KillOnClose|BreakawayOk);
            launcher=Spawn("launcher",folder,Suspended|Detached);
            if(outer!=IntPtr.Zero) Check(AssignProcessToJobObject(outer,launcher.process),"AssignOuterToLauncher");
            Check(AssignProcessToJobObject(inner,launcher.process),"AssignInnerToLauncher");
            Check(!Inside(GetCurrentProcess(),inner),"ObserverInInnerJob");
            if(outer!=IntPtr.Zero) Check(!Inside(GetCurrentProcess(),outer),"ObserverInOuterJob");
            Log(root,name+" observerPid="+System.Diagnostics.Process.GetCurrentProcess().Id+" observerInFixtureJobs=false outerFlags="+(outerFlags.HasValue?outerFlags.Value.ToString("X8"):"NONE"));
            Resume(ref launcher); AwaitFile(Path.Combine(folder,"child.txt"),10);
            string[] data=File.ReadAllText(Path.Combine(folder,"child.txt")).Split(' '); int pid=int.Parse(data[0]); long creation=long.Parse(data[1]);
            daemon=OpenProcess(Query|Terminate|Synchronize,false,pid); Check(daemon!=IntPtr.Zero,"OpenOwnedDaemon"); Check(Identity(daemon)==creation,"DaemonIdentityMismatch");
            AwaitFile(Path.Combine(folder,"ready.txt"),10); Check(WaitForSingleObject(daemon,0)==Timeout,"DaemonNotAliveBeforeClose");
            bool global=Inside(daemon,IntPtr.Zero),inInner=Inside(daemon,inner),inOuter=outer!=IntPtr.Zero&&Inside(daemon,outer);
            Check(!inInner,"BreakawayDidNotLeaveInner"); Check(global==outerFlags.HasValue,"UnexpectedResidualJob"); Check(inOuter==outerFlags.HasValue,"UnexpectedOuterMembership");
            Log(root,name+" created=true pid="+pid+" creation="+creation+" aliveBeforeClose=true inAnyJob="+global+" inInner="+inInner+" inOuter="+inOuter);
            if(outer!=IntPtr.Zero) { Check(CloseHandle(outer),"CloseOuterOwner"); outer=IntPtr.Zero; }
            else { Check(CloseHandle(inner),"CloseInnerOwner"); inner=IntPtr.Zero; }
            bool shouldDie=outerFlags.HasValue&&(outerFlags.Value&KillOnClose)!=0;
            uint wait=WaitForSingleObject(daemon,shouldDie?5000u:1500u); bool survived=wait==Timeout;
            Check(wait==0||wait==Timeout,"DaemonWaitFailure"); Check(survived!=shouldDie,"UnexpectedLifetimeOutcome");
            Check(Identity(daemon)==creation,"IdentityChangedAfterClose");
            File.WriteAllText(Path.Combine(folder,"result.txt"),"case="+name+"\ncreated=true\ncreation="+creation+"\npid="+pid+"\ninAnyJob="+global+"\ninInner="+inInner+"\ninOuter="+inOuter+"\nownerHandleClosed=true\nsurvived="+survived+"\nwait="+wait+"\nidentityMatch=true\n");
            Log(root,name+" ownerHandleClosed=true survived="+survived+" identityMatch=true");
        } finally {
            if(daemon!=IntPtr.Zero) { if(WaitForSingleObject(daemon,0)==Timeout) Check(TerminateProcess(daemon,78),"CleanupDaemon"); Check(WaitForSingleObject(daemon,5000)==0,"ReapDaemon"); CloseHandle(daemon); }
            Reap(ref launcher); if(inner!=IntPtr.Zero) CloseHandle(inner); if(outer!=IntPtr.Zero) CloseHandle(outer);
            Log(root,name+" cleanup=REAPED_EXACT_HANDLES");
        }
    }
    static int Main(string[] args) {
        string mode=args[0],root=Path.GetFullPath(args[1]);
        try {
            if(mode=="daemon") { File.WriteAllText(Path.Combine(root,"ready.txt"),Identity(GetCurrentProcess()).ToString()); Thread.Sleep(30000); return 0; }
            if(mode=="launcher") { PI child=Spawn("daemon",root,Suspended|Detached|Breakaway); long creation=Identity(child.process); Resume(ref child); File.WriteAllText(Path.Combine(root,"child.txt"),child.pid+" "+creation); CloseHandle(child.process); Thread.Sleep(30000); return 0; }
            int level=int.Parse(mode); Log(root,"bootstrapLevel="+level+" pid="+System.Diagnostics.Process.GetCurrentProcess().Id+" inAnyJob="+Inside(GetCurrentProcess(),IntPtr.Zero));
            if(Inside(GetCurrentProcess(),IntPtr.Zero)) {
                if(level>=6) throw new Exception("Cannot establish no-residual observer without changing host state");
                PI next=Spawn((level+1).ToString(),root,Suspended|Detached|Breakaway); Resume(ref next);
                uint wait=WaitForSingleObject(next.process,45000); if(wait!=0) { Reap(ref next); throw new Exception("Bootstrap child timeout"); } CloseHandle(next.process);
                return File.Exists(Path.Combine(root,"PASS.txt"))?0:1;
            }
            Log(root,"observerNoResidualJob=PROVEN");
            Case(root,"no-residual",null); Case(root,"harmless-outer",0); Case(root,"kill-outer",KillOnClose);
            File.WriteAllText(Path.Combine(root,"PASS.txt"),"ALL_THREE_CASES_AND_EXACT_HANDLE_CLEANUP_PASS"); return 0;
        } catch(Exception ex) { File.AppendAllText(Path.Combine(root,"ERROR.txt"),ex.ToString()+Environment.NewLine); return 1; }
    }
}
