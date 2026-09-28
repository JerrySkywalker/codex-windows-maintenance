param([Parameter(Mandatory)][string]$CandidateMapping,
      [Parameter(Mandatory)][string]$Python)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Candidate Windows qualification requires Windows' }
$harness = Join-Path (Split-Path -Parent $PSScriptRoot) 'harness/windows-presentation'
& $Python -B (Join-Path $harness 'qualify_candidate.py') --mapping $CandidateMapping `
    --pwsh (Get-Process -Id $PID).Path
if ($LASTEXITCODE -ne 0) { throw 'Candidate qualification failed; see selected evidence directory' }
