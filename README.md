# Codex Windows maintenance

This is community downstream maintenance tooling for a repeatable Windows compatibility workflow for the
`codex-windows-patched` downstream fork of [OpenAI Codex](https://github.com/openai/codex). It contains
scripts, local test fixtures, and a source mapping. It contains no Codex source
or packaged executables. This is not an official OpenAI product and does not
imply upstream endorsement.

The checked-in `manifest.json` binds the upstream 0.156.0 commit to the public
downstream release tag and its qualified source tree. Reproduction starts with a fresh clone of
the downstream source, PowerShell 7, Python 3, Rust, Git, and `just`.
The source repository's own package builder supplies the package layout and
pinned resource checksums.

```powershell
git clone https://github.com/ACCOUNT/codex-windows-patched.git source-clone
git -C source-clone checkout --detach v0.156.0-wbp-r1
./scripts/bootstrap.ps1 -SourcePath source-clone -PackageDir package-output
./scripts/qualify.ps1 -SourcePath source-clone -PackageDir package-output
./scripts/port.ps1 -SourcePath source-clone -UpstreamRef NEW_UPSTREAM_REF -UpstreamVersion NEW_VERSION
```

Replace `ACCOUNT` with the public source fork's account and choose output
directories outside this maintenance checkout.

`bootstrap.ps1` verifies the exact source tag, commit, and tree before invoking the
source package builder. It always qualifies the package. Pass `-InstallDir` to
copy it into a new side-by-side directory and qualify that installed copy.
`qualify.ps1` records file hashes and runs an isolated
local Responses, MCP, hook, shell, Git, and bundled `rg` smoke with a window
event observer. Its receipt reports `ISOLATED_SMOKE_PASS`; a separate visible
positive control and fresh-clone build are required for a complete release
qualification. `port.ps1` reports changed spawn sites for manual review; it
does not apply a patch automatically. Output and test homes live under a
caller-selected directory or a fresh temporary directory. None of the scripts
switch an installed Codex selection or manage a production daemon.

`harness/windows-presentation/POLICY.md` records the intended background and
interactive boundaries. Keep historical qualification receipts outside Git.
GitHub Actions checks file structure and syntax on Windows; it does not build
Codex or claim full upstream test coverage.

The source fork preserves the upstream Apache-2.0 license and attribution.
This maintenance repository is also licensed under Apache-2.0.
