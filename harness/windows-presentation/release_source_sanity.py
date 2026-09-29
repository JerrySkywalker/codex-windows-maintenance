"""Derive a release lock correction from exact upstream objects, never Cargo output."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

from candidate_mapping import git, read_json, require, sha
from rolling_control import CONTROL, exact
from validation_job import verify_receipt


def normalize(lock, local_names, version):
    chunks = lock.split(b"[[package]]")
    result, seen, changed = [chunks[0]], set(), []
    for raw in chunks[1:]:
        record = tomllib.loads((b"[[package]]" + raw).decode())["package"][0]
        updated = raw
        if "source" not in record:
            name = record["name"]
            require(name in local_names and name not in seen and "checksum" not in record,
                    "Unexpected/duplicate local lock record")
            seen.add(name)
            require(record["version"] in ("0.0.0", version), "Unexpected local version drift")
            if record["version"] != version:
                old = b'version = "0.0.0"'
                require(raw.count(old) == 1, "Ambiguous local version field")
                updated = raw.replace(old, f'version = "{version}"'.encode(), 1)
                changed.append(name)
            expected = dict(record, version=version)
            require(tomllib.loads((b"[[package]]" + updated).decode())["package"][0] == expected,
                    "Local non-version fields changed")
        result.append(updated)
    require(seen == set(local_names), "Lock and workspace-local package sets differ")
    return b"[[package]]".join(result), changed


def derive(source, upstream):
    exact(upstream)
    control = read_json(CONTROL)
    require(upstream == control["targetUpstream"]["commit"], "Unadmitted release upstream")
    def obj(path):
        return subprocess.check_output(["git", "-C", str(source), "show", f"{upstream}:{path}"])
    manifest = obj("codex-rs/Cargo.toml")
    workspace = tomllib.loads(manifest.decode())["workspace"]
    version = workspace["package"]["version"]
    require(version == control["targetUpstream"]["version"], "Release version mismatch")
    paths = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-r", "--name-only",
                                     upstream, "codex-rs"]).decode().splitlines()
    names = {}
    for path in paths:
        if path.endswith("/Cargo.toml"):
            package = tomllib.loads(obj(path).decode()).get("package", {})
            if package.get("version") == {"workspace": True}:
                require(package["name"] not in names, "Duplicate workspace package")
                names[package["name"]] = path
    lock = obj("codex-rs/Cargo.lock")
    normalized, changed = normalize(lock, names, version)
    digest = lambda data: hashlib.sha256(data).hexdigest()
    return normalized, {"schemaVersion": 1, "upstreamCommit": upstream, "workspaceVersion": version,
                        "localPackages": names, "localVersionChanges": sorted(changed),
                        "upstreamLockSha256": digest(lock), "normalizedLockSha256": digest(normalized),
                        "cargoTomlSha256": digest(manifest), "externalRecordChanges": 0,
                        "dependencyEdgeChanges": 0, "status": "NORMALIZATION_PROOF_ONLY"}


def verify_gate(source, upstream, jobs):
    normalized, proof = derive(source, upstream)
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "Clean release source required")
    lock = (source / "codex-rs/Cargo.lock").read_bytes().replace(b"\r\n", b"\n")
    manifest = (source / "codex-rs/Cargo.toml").read_bytes().replace(b"\r\n", b"\n")
    require(lock == normalized and hashlib.sha256(manifest).hexdigest() == proof["cargoTomlSha256"],
            "Candidate changed beyond exact release-source normalization")
    commit, tree = git(source, "rev-parse", "HEAD"), git(source, "show", "-s", "--format=%T", "HEAD")
    git(source, "merge-base", "--is-ancestor", upstream, commit)
    results = []
    for directory in jobs:
        request, _ = verify_receipt(directory, "PASS")
        require(request["source"]["commit"] == commit and request["source"]["tree"] == tree,
                "Locked command receipt mismatch")
        require(Path(request["command"][0]).name.lower() == "cargo.exe" and
                Path(request["cwd"]).resolve() == (source / "codex-rs").resolve(), "Direct Cargo command required")
        results.append((request["command"], directory))
    metadata_jobs = [directory for command, directory in results if command[1:] ==
                     ["metadata", "--locked", "--format-version", "1"] and
                     read_json(directory / "request.json").get("machineJson") is True]
    check_jobs = [directory for command, directory in results if command[1:] ==
                  ["check", "--locked", "-p", "codex-utils-pty", "--lib"]]
    require(len(metadata_jobs) == 1 and len(check_jobs) == 1,
            "Full locked metadata and locked check required")
    metadata = read_json(metadata_jobs[0] / "command.log")
    packages = {package["id"]: package for package in metadata["packages"]}
    local = [packages[member] for member in metadata["workspace_members"]]
    require({package["name"] for package in local} == set(proof["localPackages"]) and
            all(package["version"] == proof["workspaceVersion"] and package["source"] is None for package in local),
            "Full Cargo workspace membership differs from lock proof")
    proof.update(status="RELEASE_SOURCE_SANITY_PASS", sourceCommit=commit, sourceTree=tree,
                 lockedReceipts={str(directory): sha(directory / "receipt.json") for directory in jobs})
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--locked-job", type=Path, action="append", default=[])
    args = parser.parse_args()
    require(args.output.is_absolute() and not args.output.exists() and
            args.source.resolve() not in args.output.resolve().parents, "Fresh external proof path required")
    normalized, proof = derive(args.source, args.upstream)
    if args.locked_job:
        proof = verify_gate(args.source, args.upstream, args.locked_job)
    args.output.mkdir()
    (args.output / "normalized-Cargo.lock").write_bytes(normalized)
    (args.output / "proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"Local version corrections: {len(proof['localVersionChanges'])}; external/edge changes: 0")


if __name__ == "__main__":
    main()
