param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$Commit,
    [Parameter(Mandatory)][string]$Tree,
    [Parameter(Mandatory)][string]$Just,
    [Parameter(Mandatory)][string]$Cargo,
    [Parameter(Mandatory)][string]$Toolchain,
    [Parameter(Mandatory)][string]$CargoHome,
    [Parameter(Mandatory)][string]$RustupHome,
    [Parameter(Mandatory)][string]$TargetDir,
    [Parameter(Mandatory)][string]$OutputDir,
    [string[]]$DependencyPath = @(),
    [switch]$FullSuite,
    [string]$DurableJob,
    [string[]]$TestArgs = @('-p', 'codex-utils-pty', '-p', 'codex-app-server-daemon', '--lib')
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$arguments = @('-B', (Join-Path $repoRoot 'harness/windows-presentation/source_validation.py'),
    '--source', $Source, '--commit', $Commit, '--tree', $Tree, '--just', $Just, '--cargo', $Cargo,
    '--toolchain', $Toolchain, '--cargo-home', $CargoHome, '--rustup-home', $RustupHome,
    '--target-dir', $TargetDir, '--output', $OutputDir)
foreach ($path in $DependencyPath) { $arguments += @('--dependency-path', $path) }
if ($FullSuite) {
    if (-not $DurableJob) { throw 'Full qualification requires a durable external job receipt directory' }
    $arguments += @('--durable-job', $DurableJob)
    $arguments += @('--full-suite')
    if (-not $PSBoundParameters.ContainsKey('TestArgs')) { $TestArgs = @() }
}
$arguments += @('--') + $TestArgs
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Source native/nextest validation failed' }
