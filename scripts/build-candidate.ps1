param([Parameter(Mandatory)][string]$CandidateMapping,
      [Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
$validator = Join-Path (Split-Path -Parent $PSScriptRoot) 'harness/windows-presentation/candidate_mapping.py'
$json = & $Python -B $validator $CandidateMapping --mode build
if ($LASTEXITCODE -ne 0) { throw 'Candidate admission failed' }
$mapping = $json | ConvertFrom-Json
$mappingHash = (Get-FileHash -LiteralPath $CandidateMapping -Algorithm SHA256).Hash
Push-Location $mapping.sourcePath
try {
    & just --set python $Python assemble-codex-package --target $mapping.target --variant $mapping.packageVariant `
        --package-version $mapping.upstreamVersion --cargo-profile $mapping.cargoProfile --package-dir $mapping.packageDir
    if ($LASTEXITCODE -ne 0) { throw 'Candidate package build failed' }
} finally { Pop-Location }
# Recheck source identity/cleanliness before issuing build provenance.
$head = (& git -C $mapping.sourcePath rev-parse HEAD).Trim()
$tree = (& git -C $mapping.sourcePath show -s --format=%T HEAD).Trim()
$dirty = @(& git -C $mapping.sourcePath status --porcelain=v1 --untracked-files=all)
if ($head -ne $mapping.downstreamCommit -or $tree -ne $mapping.downstreamTree -or $dirty.Count) {
    throw 'Source changed during candidate build'
}
if ((Get-FileHash -LiteralPath $CandidateMapping -Algorithm SHA256).Hash -ne $mappingHash) {
    throw 'Candidate mapping changed during build'
}
& $Python -B $validator $CandidateMapping --mode record-build
if ($LASTEXITCODE -ne 0) { throw 'Candidate provenance recording failed' }
& (Join-Path $PSScriptRoot 'qualify-candidate.ps1') -CandidateMapping $CandidateMapping -Python $Python
if (-not $?) { throw 'Candidate qualification failed' }
