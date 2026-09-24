param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$UpstreamRef,
    [Parameter(Mandatory)][string]$UpstreamVersion,
    [string]$OutputPath = (Join-Path $env:TEMP 'codex-windows-port-review.txt')
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'manifest.json') -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $SourcePath).Path
& git -C $source cat-file -e "$UpstreamRef^{commit}"
if ($LASTEXITCODE -ne 0) { throw "Unknown upstream ref: $UpstreamRef" }
$upstream = (& git -C $source rev-parse $UpstreamRef).Trim()
$changed = @(& git -C $source diff --name-only $manifest.upstreamCommit $upstream -- codex-rs)
if ($LASTEXITCODE -ne 0) { throw 'Upstream diff failed' }
$spawnSites = @($changed | Where-Object { $_ -like '*.rs' -and (Test-Path -LiteralPath (Join-Path $source $_)) } |
    Where-Object { & rg -q 'Command::new|CreateProcessW|CreateProcessAsUserW|spawn\(' (Join-Path $source $_); $LASTEXITCODE -eq 0 })
$policy = Join-Path $repoRoot 'harness\windows-presentation\POLICY.md'
$inventory = Join-Path $repoRoot 'harness\windows-presentation\SPAWN-INVENTORY.md'
$lines = @(
    "upstream_version=$UpstreamVersion"
    "baseline=$($manifest.upstreamCommit)"
    "candidate=$upstream"
    "policy_sha256=$((Get-FileHash -LiteralPath $policy -Algorithm SHA256).Hash.ToLowerInvariant())"
    "inventory_sha256=$((Get-FileHash -LiteralPath $inventory -Algorithm SHA256).Hash.ToLowerInvariant())"
    "changed_source_files=$($changed.Count)"
    'changed_paths:'
) + $changed + @('touched_spawn_site_paths:') + $spawnSites
$output = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output) | Out-Null
$lines | Set-Content -LiteralPath $output -Encoding utf8
Write-Output "PORT_REVIEW=$output"
Write-Output 'Review every changed launch boundary against harness/windows-presentation/POLICY.md before updating manifest.json.'
