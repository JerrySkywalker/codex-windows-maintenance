param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$PackageDir,
    [string]$Python,
    [string]$QualificationDir = (Join-Path $env:TEMP ([IO.Path]::GetRandomFileName())),
    [string]$InstallDir
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
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot 'manifest.json') -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $SourcePath).Path
$head = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $manifest.downstreamCommit) {
    throw "Expected source commit $($manifest.downstreamCommit); found $head"
}
$tag = (& git -C $source rev-parse "$($manifest.downstreamTag)^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $tag -ne $head) {
    throw "Expected source tag $($manifest.downstreamTag) at $head"
}
$tree = (& git -C $source show -s --format=%T HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $tree -ne $manifest.downstreamTree) {
    throw "Expected source tree $($manifest.downstreamTree); found $tree"
}
if (@(& git -C $source status --porcelain).Count -ne 0) {
    throw 'Source checkout must be clean'
}
foreach ($command in @('git', 'just', 'cargo', $Python)) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command unavailable: $command"
    }
}
$package = [IO.Path]::GetFullPath($PackageDir)
if ($package.StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Package output must be outside the source checkout'
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $package) | Out-Null
Push-Location $source
try {
    & just --set python $Python assemble-codex-package --target $manifest.target --variant $manifest.packageVariant `
        --package-version $manifest.upstreamVersion --cargo-profile $manifest.cargoProfile `
        --package-dir $package
    if ($LASTEXITCODE -ne 0) { throw 'Source package build failed' }
} finally {
    Pop-Location
}
& (Join-Path $PSScriptRoot 'qualify.ps1') -SourcePath $source -PackageDir $package -Python $Python `
    -OutputDir (Join-Path $QualificationDir 'isolated')
if (-not $?) { throw 'Package qualification failed' }
if ($InstallDir) {
    $install = [IO.Path]::GetFullPath($InstallDir)
    if ($install -eq $source -or $install -eq $package -or
        $install.StartsWith($source + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        $install.StartsWith($package + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Install directory must be separate from source and package output'
    }
    if (Test-Path -LiteralPath $install) { throw "Install directory already exists: $install" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $install) | Out-Null
    Copy-Item -LiteralPath $package -Destination $install -Recurse
    & (Join-Path $PSScriptRoot 'qualify.ps1') -SourcePath $source -PackageDir $install -Python $Python `
        -OutputDir (Join-Path $QualificationDir 'installed')
    if (-not $?) { throw 'Installed package qualification failed' }
    Write-Output "INSTALL_DIR=$install"
}
Write-Output "PACKAGE_DIR=$package"
