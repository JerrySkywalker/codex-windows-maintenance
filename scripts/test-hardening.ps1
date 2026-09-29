param([Parameter(Mandatory)][string]$Python,
      [Parameter(Mandatory)][string]$OutputDir)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDir) { throw 'Validation output already exists' }
New-Item -ItemType Directory -Path $OutputDir | Out-Null
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'harness/windows-presentation/test_hardening.py') -PathType Leaf)) {
    throw 'Focused test suite is missing'
}
$errorsFound = @()
foreach ($path in (Get-ChildItem (Join-Path $repoRoot 'scripts'),(Join-Path $repoRoot 'harness') -Recurse -Filter '*.ps1').FullName) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    $errorsFound += $errors
}
if ($errorsFound.Count) { throw "PowerShell syntax errors: $errorsFound" }
Push-Location $repoRoot
try {
    & $Python -B -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8-sig')) for p in pathlib.Path('harness').rglob('*.py')]"
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax validation failed' }
    & $Python -B -c "import unittest, sys; loader = unittest.TestLoader(); suite = unittest.TestSuite(loader.discover('harness/windows-presentation', pattern=p) for p in ('test_hardening.py', 'test_source_fixture*.py', 'test_rolling.py')); assert suite.countTestCases() > 0, 'Focused suite is empty'; sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())" *> (Join-Path $OutputDir 'unit-tests.log')
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath (Join-Path $OutputDir 'unit-tests.log') | Write-Output
        throw 'Focused hardening tests failed'
    }
} finally { Pop-Location }
@{status='FOCUSED_VALIDATION_PASS'; scope='Syntax and deterministic harness tests; candidate package/runtime qualification not claimed'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDir 'validation.json') -Encoding utf8
