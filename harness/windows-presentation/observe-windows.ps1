param(
    [Parameter(Mandatory)][string]$OutputPath,
    [int]$DurationSeconds = 15
)

$source = @'
using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class CodexWindowObserver {
    private delegate void WinEventProc(IntPtr hook, uint eventType, IntPtr hwnd, int objectId, int childId, uint threadId, uint eventTime);
    private static readonly WinEventProc callback = OnEvent;
    private static readonly ConcurrentQueue<string> events = new ConcurrentQueue<string>();
    private static IntPtr hook;

    [DllImport("user32.dll")]
    private static extern IntPtr SetWinEventHook(uint eventMin, uint eventMax, IntPtr module, WinEventProc callback, uint processId, uint threadId, uint flags);
    [DllImport("user32.dll")]
    private static extern bool UnhookWinEvent(IntPtr hook);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hwnd, StringBuilder className, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hwnd, StringBuilder title, int maxCount);
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    private static extern bool PeekMessage(out Message message, IntPtr hwnd, uint min, uint max, uint remove);

    [StructLayout(LayoutKind.Sequential)]
    private struct Point { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)]
    private struct Message { public IntPtr Hwnd; public uint Msg; public IntPtr WParam; public IntPtr LParam; public uint Time; public Point Pt; }

    public static void Start() {
        // EVENT_SYSTEM_FOREGROUND..EVENT_OBJECT_HIDE, out-of-context across this desktop.
        hook = SetWinEventHook(0x0003, 0x8003, IntPtr.Zero, callback, 0, 0, 0);
        if (hook == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    }

    public static void Pump() {
        Message message;
        while (PeekMessage(out message, IntPtr.Zero, 0, 0, 1)) { }
    }

    public static string[] Drain() {
        var result = new System.Collections.Generic.List<string>();
        string line;
        while (events.TryDequeue(out line)) result.Add(line);
        return result.ToArray();
    }

    public static void Stop() { if (hook != IntPtr.Zero) { UnhookWinEvent(hook); hook = IntPtr.Zero; } }

    private static void OnEvent(IntPtr h, uint eventType, IntPtr hwnd, int objectId, int childId, uint threadId, uint eventTime) {
        if (hwnd == IntPtr.Zero || objectId != 0 || childId != 0) return;
        if (eventType != 0x0003 && eventType != 0x8000 && eventType != 0x8002 && eventType != 0x8003) return;
        uint pid;
        GetWindowThreadProcessId(hwnd, out pid);
        if (pid == 0) return;
        string name = "";
        string started = "";
        try {
            using (var process = Process.GetProcessById((int)pid)) {
                name = process.ProcessName;
                started = process.StartTime.ToUniversalTime().ToString("O");
            }
        } catch { }
        var className = new StringBuilder(256);
        var title = new StringBuilder(256);
        GetClassName(hwnd, className, className.Capacity);
        GetWindowText(hwnd, title, title.Capacity);
        var line = String.Join("\t", DateTime.UtcNow.ToString("O"), eventType.ToString("X4"), pid.ToString(),
            started, name, hwnd.ToInt64().ToString("X"), className.ToString().Replace('\t', ' '),
            title.ToString().Replace('\t', ' '), (GetForegroundWindow() == hwnd).ToString());
        events.Enqueue(line);
    }
}
'@

Add-Type -TypeDefinition $source -ErrorAction Stop
$parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
"utc`twin_event`tpid`tprocess_started_utc`tprocess`twindow_hex`tclass`ttitle`tforeground_at_callback" | Set-Content -LiteralPath $OutputPath -Encoding utf8
[CodexWindowObserver]::Start()
try {
    $until = [DateTime]::UtcNow.AddSeconds($DurationSeconds)
    while ([DateTime]::UtcNow -lt $until) {
        [CodexWindowObserver]::Pump()
        $lines = [CodexWindowObserver]::Drain()
        if ($lines.Length -gt 0) { Add-Content -LiteralPath $OutputPath -Value $lines -Encoding utf8 }
        Start-Sleep -Milliseconds 10
    }
} finally {
    [CodexWindowObserver]::Stop()
    $lines = [CodexWindowObserver]::Drain()
    if ($lines.Length -gt 0) { Add-Content -LiteralPath $OutputPath -Value $lines -Encoding utf8 }
}
