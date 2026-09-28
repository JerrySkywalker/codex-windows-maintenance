param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$PackageDir,
    [string]$Python,
    [string]$CandidateMapping,
    [string]$OutputDir = (Join-Path $env:TEMP ([IO.Path]::GetRandomFileName()))
)

$ErrorActionPreference = 'Stop'
if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = (& py -3 -c 'import sys; print(sys.executable)').Trim()
    } else {
        $Python = (Get-Command python -ErrorAction Stop).Source
    }
}
& $Python --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Python unavailable: $Python" }
$repoRoot = Split-Path -Parent $PSScriptRoot
$harness = Join-Path $repoRoot 'harness\windows-presentation'
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'manifest.json') -Raw | ConvertFrom-Json
if ($CandidateMapping) {
    $candidateJson = & $Python -B (Join-Path $harness 'candidate_mapping.py') $CandidateMapping --mode qualify
    if ($LASTEXITCODE -ne 0) { throw 'Candidate admission failed' }
    $manifest = $candidateJson | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($SourcePath) -ne [IO.Path]::GetFullPath($manifest.sourcePath) -or
        [IO.Path]::GetFullPath($PackageDir) -ne [IO.Path]::GetFullPath($manifest.packageDir) -or
        [IO.Path]::GetFullPath($OutputDir) -ne (Join-Path ([IO.Path]::GetFullPath($manifest.outputDir)) 'no-daemon')) {
        throw 'Candidate smoke paths must match its mapping'
    }
}
$source = (Resolve-Path -LiteralPath $SourcePath).Path
$package = (Resolve-Path -LiteralPath $PackageDir).Path
$runRoot = [IO.Path]::GetFullPath($OutputDir)
$head = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $manifest.downstreamCommit) { throw 'Source commit mismatch' }
if (-not $CandidateMapping) {
    $tag = (& git -C $source rev-parse "$($manifest.downstreamTag)^{commit}").Trim()
    if ($LASTEXITCODE -ne 0 -or $tag -ne $head) { throw 'Source tag mismatch' }
}
$tree = (& git -C $source show -s --format=%T HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $tree -ne $manifest.downstreamTree) { throw 'Source tree mismatch' }
if (Test-Path -LiteralPath $runRoot) { throw "Output directory already exists: $runRoot" }
New-Item -ItemType Directory -Path $runRoot | Out-Null
$workspace = Join-Path $runRoot 'workspace'
$codexHome = Join-Path $runRoot 'home'
New-Item -ItemType Directory -Path $workspace,$codexHome | Out-Null
& git -C $workspace init | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Disposable workspace init failed' }

$expectedFiles = @(
    'bin/codex.exe', 'bin/codex-code-mode-host.exe',
    'codex-resources/codex-command-runner.exe',
    'codex-resources/codex-windows-sandbox-setup.exe',
    'codex-path/rg.exe', 'codex-package.json'
)
$files = foreach ($relativePath in $expectedFiles) {
    $path = Join-Path $package $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing package file: $relativePath" }
    [ordered]@{ path=$relativePath; sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$metadata = Get-Content -LiteralPath (Join-Path $package 'codex-package.json') -Raw | ConvertFrom-Json
if ($metadata.version -ne $manifest.upstreamVersion -or $metadata.target -ne $manifest.target -or
    $metadata.entrypoint -ne 'bin/codex.exe') { throw 'Package metadata mismatch' }

function Start-HiddenProcess([string]$FileName, [string[]]$Arguments) {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FileName
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $Arguments) { [void]$startInfo.ArgumentList.Add($argument) }
    return [Diagnostics.Process]::Start($startInfo)
}

function Read-Exact([IO.Stream]$Stream, [int]$Length) {
    $buffer = [byte[]]::new($Length)
    $offset = 0
    while ($offset -lt $Length) {
        $read = $Stream.Read($buffer, $offset, $Length - $offset)
        if ($read -eq 0) { throw 'Unexpected Code Mode EOF' }
        $offset += $read
    }
    return ,$buffer
}

function Test-CodeModeHandshake {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = Join-Path $package 'bin/codex-code-mode-host.exe'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    [void]$startInfo.ArgumentList.Add('--listen')
    [void]$startInfo.ArgumentList.Add('stdio')
    $process = [Diagnostics.Process]::Start($startInfo)
    try {
        $hello = @{ type='connection/hello'; supportedVersions=@(1); requiredCapabilities=@(); optionalCapabilities=@('session-cell-execution-resource-limits') } | ConvertTo-Json -Compress
        $payload = [Text.UTF8Encoding]::new($false).GetBytes($hello)
        $prefix = [BitConverter]::GetBytes([uint32]$payload.Length)
        $process.StandardInput.BaseStream.Write($prefix, 0, $prefix.Length)
        $process.StandardInput.BaseStream.Write($payload, 0, $payload.Length)
        $process.StandardInput.BaseStream.Flush()
        $responsePrefix = Read-Exact $process.StandardOutput.BaseStream 4
        $responseLength = [BitConverter]::ToUInt32($responsePrefix, 0)
        if ($responseLength -gt 1048576) { throw 'Code Mode response exceeds limit' }
        $responseBytes = Read-Exact $process.StandardOutput.BaseStream $responseLength
        $response = [Text.Encoding]::UTF8.GetString($responseBytes) | ConvertFrom-Json
        if ($response.type -ne 'connection/ready' -or $response.selectedVersion -ne 1) {
            throw 'Code Mode handshake failed'
        }
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(10000) -or $process.ExitCode -ne 0) { throw 'Code Mode host did not exit cleanly' }
    } finally {
        if (-not $process.HasExited) { $process.Kill($true) }
        $process.Dispose()
    }
}

$config = @"
cli_auth_credentials_store = "file"
mcp_oauth_credentials_store = "file"

[features]
hooks = true

[mcp_servers.package_smoke]
command = '$($Python.Replace("'", "''"))'
args = ['$((Join-Path $harness 'mcp_smoke_server.py').Replace("'", "''"))', '$((Join-Path $runRoot 'mcp-lifecycle.jsonl').Replace("'", "''"))']
startup_timeout_sec = 10
tool_timeout_sec = 10

[projects.'$($workspace.Replace("'", "''"))']
trust_level = 'trusted'
"@
$config | Set-Content -LiteralPath (Join-Path $codexHome 'config.toml') -Encoding utf8
$hookCommand = '& "' + $Python + '" "' + (Join-Path $harness 'hook_smoke.py') + '" "' + (Join-Path $runRoot 'hook-lifecycle.jsonl') + '"'
@{ hooks = @{ PreToolUse = @(@{ matcher = '^Bash$'; hooks = @(@{ type = 'command'; command = $hookCommand }) }) } } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $codexHome 'hooks.json') -Encoding utf8

$portFile = Join-Path $runRoot 'responses-port.txt'
$requestLog = Join-Path $runRoot 'responses-requests.jsonl'
$shellMarker = Join-Path $runRoot 'shell-marker.txt'
$eventFile = Join-Path $runRoot 'windows.tsv'
$server = $null
$observer = $null
$observerStop = Join-Path $runRoot 'observer.stop'
$observerReady = Join-Path $runRoot 'observer.ready'
$oldHome = $env:CODEX_HOME
$oldKey = $env:OPENAI_API_KEY
$oldPath = $env:PATH
try {
    $server = Start-HiddenProcess $Python @(
        (Join-Path $harness 'mock_responses.py'), '--port-file', $portFile,
        '--request-log', $requestLog, '--workspace', $workspace,
        '--shell-marker', $shellMarker
    )
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-Path -LiteralPath $portFile)) {
        if ($server.HasExited -or [DateTime]::UtcNow -ge $deadline) { throw 'Mock Responses server did not start' }
        Start-Sleep -Milliseconds 50
    }
    $port = (Get-Content -LiteralPath $portFile -Raw).Trim()
    $observer = Start-HiddenProcess (Get-Process -Id $PID).Path @(
        '-NoProfile', '-File', (Join-Path $harness 'observe-windows.ps1'),
        '-OutputPath', $eventFile, '-DurationSeconds', '180',
        '-ReadyPath', $observerReady, '-StopPath', $observerStop
    )
    $observerDeadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-Path -LiteralPath $observerReady)) {
        if ($observer.HasExited -or [DateTime]::UtcNow -ge $observerDeadline) { throw 'Window observer did not become ready' }
        Start-Sleep -Milliseconds 20
    }
    $startedAt = [DateTimeOffset]::UtcNow
    Start-Sleep -Seconds 1
    Test-CodeModeHandshake
    $env:CODEX_HOME = $codexHome
    $env:OPENAI_API_KEY = 'local-smoke-only'
    $env:PATH = (Join-Path $package 'codex-path') + [IO.Path]::PathSeparator + $oldPath
    $provider = "model_providers.mock={ name = `"mock`", base_url = `"http://127.0.0.1:$port/v1`", env_key = `"OPENAI_API_KEY`", wire_api = `"responses`" }"
    & (Join-Path $package 'bin/codex.exe') --no-daemon exec --skip-git-repo-check --ephemeral `
        --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust `
        --disable code_mode -c $provider -c 'model_provider="mock"' -m 'gpt-5.5' `
        -C $workspace 'Run the bounded package smoke commands supplied by the local test endpoint.' `
        *> (Join-Path $runRoot 'codex-exec.log')
    if ($LASTEXITCODE -ne 0) { throw "Codex smoke failed: $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $shellMarker)) { throw 'Shell smoke marker missing' }
    if (-not $server.WaitForExit(10000)) { throw 'Mock Responses server did not finish' }
    if ($observer.HasExited) { throw 'Window observer ended before no-daemon workload completed' }
    'WORKLOAD_COMPLETE' | Set-Content -LiteralPath $observerStop -Encoding ascii
    if (-not $observer.WaitForExit(15000) -or $observer.ExitCode -ne 0) { throw 'Window observer failed' }
    $observation = Get-Content -Raw -LiteralPath ($observerStop + '.done.json') | ConvertFrom-Json
    if (-not $observation.stopMarkerObserved) { throw 'Window observer interval incomplete' }
    $requests = @(Get-Content -LiteralPath $requestLog | ForEach-Object { $_ | ConvertFrom-Json })
    if ($requests.Count -ne 4) { throw "Expected four model requests; got $($requests.Count)" }
    $responses = $requests | ConvertTo-Json -Depth 100 -Compress
    if ($responses -notmatch 'shell-ok' -or $responses -notmatch 'codex-path') { throw 'Shell or bundled rg result missing' }
    $gitResponse = $requests[2].body | ConvertTo-Json -Depth 100 -Compress
    if ($gitResponse -notmatch [regex]::Escape($workspace.Replace('\', '\\'))) {
        throw 'Git smoke result did not identify the disposable workspace'
    }
    $mcp = @(Get-Content -LiteralPath (Join-Path $runRoot 'mcp-lifecycle.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
    if ($mcp.event -notcontains 'start' -or $mcp.method -notcontains 'initialize' -or
        $mcp.method -notcontains 'tools/list') { throw 'MCP lifecycle incomplete' }
    $hooks = @(Get-Content -LiteralPath (Join-Path $runRoot 'hook-lifecycle.jsonl') | ForEach-Object { $_ | ConvertFrom-Json })
    if ($hooks.Count -lt 3) { throw 'PreToolUse hook count too low' }
    $events = @(Import-Csv -LiteralPath $eventFile -Delimiter "`t")
    $names = @('codex', 'codex-code-mode-host', 'codex-command-runner', 'git', 'pwsh', 'powershell', 'python', 'rg', 'conhost', 'OpenConsole')
    $relevant = @($events | Where-Object {
        $_.process -in $names -and $_.process_started_utc -and
        ([DateTimeOffset]::Parse($_.process_started_utc) -ge $startedAt.AddSeconds(-1))
    })
    $visible = @($relevant | Where-Object { $_.win_event -in @('0003','8002') -or $_.class -match 'ConsoleWindowClass|PseudoConsoleWindow' })
    if ($visible.Count -ne 0) { throw "Observed $($visible.Count) visible or foreground events" }
    [ordered]@{ status='ISOLATED_SMOKE_PASS'; sourceCommit=$head; sourceTree=$tree; packageFiles=@($files); codeModeHandshake='PASS'; modelRequests=$requests.Count; mcpEvents=$mcp.Count; hookEvents=$hooks.Count; relevantWindowEvents=$relevant.Count; visibleWindowEvents=$visible.Count; positiveControl='NOT_RUN' } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot 'qualification.json') -Encoding utf8
    Write-Output "QUALIFICATION=ISOLATED_SMOKE_PASS RECEIPT=$(Join-Path $runRoot 'qualification.json')"
} finally {
    $env:CODEX_HOME = $oldHome
    $env:OPENAI_API_KEY = $oldKey
    $env:PATH = $oldPath
    if ($server -and -not $server.HasExited) { $server.Kill($true) }
    if ($observer -and -not $observer.HasExited) { $observer.Kill($true) }
    if ($server) { $server.Dispose() }
    if ($observer) { $observer.Dispose() }
}
