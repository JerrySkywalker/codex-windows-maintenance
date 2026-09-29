"""Fail-closed, explicitly unreleased source/package mapping. No install operations."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ("bin/codex.exe", "bin/codex-code-mode-host.exe",
         "codex-resources/codex-command-runner.exe",
         "codex-resources/codex-windows-sandbox-setup.exe",
         "codex-path/rg.exe", "codex-package.json")
FIELDS = {"schemaVersion", "kind", "goalId", "upstreamVersion", "upstreamCommit",
          "downstreamCommit", "downstreamTree", "target", "packageVariant",
          "cargoProfile", "sourcePath", "packageDir", "outputDir"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def git(source, *args):
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True,
                            text=True, encoding="utf-8", timeout=30,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, f"Git verification failed: {args}")
    return result.stdout.strip()


def contained(path, parent):
    return path == parent or parent in path.parents


def load(path, mode="qualify"):
    mapping = read_json(path)
    require(set(mapping) == FIELDS, "Incomplete or unknown candidate mapping fields")
    require(type(mapping["schemaVersion"]) is int and mapping["schemaVersion"] == 1 and mapping["kind"] == "UNRELEASED_CANDIDATE",
            "Candidate cannot claim released status")
    train = read_json(ROOT / "goals/WBP-ROLLING-0159-FAST-FORWARD-001.manifest.json")
    require(mapping["goalId"] == train["goalId"], "Candidate goal not admitted")
    target = train["targetUpstream"]
    require((mapping["upstreamVersion"], mapping["upstreamCommit"]) ==
            (target["version"], target["commit"]), "Upstream mapping not admitted")
    for field in ("upstreamCommit", "downstreamCommit", "downstreamTree"):
        require(isinstance(mapping[field], str) and re.fullmatch(r"[0-9a-f]{40}", mapping[field]),
                f"Exact lowercase object ID required: {field}")
    require((mapping["target"], mapping["packageVariant"], mapping["cargoProfile"]) ==
            ("x86_64-pc-windows-msvc", "codex", "release"), "Unsupported package configuration")
    paths = {}
    for field in ("sourcePath", "packageDir", "outputDir"):
        require(isinstance(mapping[field], str) and Path(mapping[field]).is_absolute(),
                f"Absolute caller-selected path required: {field}")
        paths[field] = Path(mapping[field]).resolve()
    source, package, output = (paths[key] for key in ("sourcePath", "packageDir", "outputDir"))
    for dest in (package, output):
        require(not contained(dest, source) and not contained(source, dest) and
                not contained(dest, ROOT) and not contained(ROOT, dest),
                "Output must be outside both repositories")
    require(not contained(output, package) and not contained(package, output),
            "Package and evidence paths must be separate")
    require(not output.exists(), "Evidence output already exists")
    require(git(source, "rev-parse", "HEAD") == mapping["downstreamCommit"], "Source commit mismatch")
    require(git(source, "show", "-s", "--format=%T", "HEAD") == mapping["downstreamTree"], "Source tree mismatch")
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all"), "Dirty source")
    git(source, "merge-base", "--is-ancestor", mapping["upstreamCommit"], mapping["downstreamCommit"])
    if mode == "build":
        require(not package.exists(), "Build package output already exists")
    else:
        require(package.is_dir(), "Package missing")
        verify_build(path, mapping, package)
    return mapping, paths


def package_files(package):
    result = {}
    for name in FILES:
        file = package / name
        require(file.is_file() and contained(file.resolve(), package), f"Missing/escaped package file: {name}")
        result[name] = sha(file)
    return result


def record_build(path):
    mapping = read_json(path)
    source = Path(mapping["sourcePath"]).resolve()
    require(git(source, "rev-parse", "HEAD") == mapping["downstreamCommit"] and
            git(source, "show", "-s", "--format=%T", "HEAD") == mapping["downstreamTree"] and
            not git(source, "status", "--porcelain=v1", "--untracked-files=all"),
            "Source changed before build recording")
    package = Path(mapping["packageDir"]).resolve()
    write_json(package / "candidate-build.json", {
        "kind": "UNRELEASED_CANDIDATE_BUILD", "mappingSha256": sha(path),
        "downstreamCommit": mapping["downstreamCommit"], "downstreamTree": mapping["downstreamTree"],
        "files": package_files(package)})


def verify_build(path, mapping, package):
    build = read_json(package / "candidate-build.json")
    require(build.get("kind") == "UNRELEASED_CANDIDATE_BUILD" and
            build.get("mappingSha256") == sha(path) and
            build.get("downstreamCommit") == mapping["downstreamCommit"] and
            build.get("downstreamTree") == mapping["downstreamTree"] and
            build.get("files") == package_files(package), "Candidate build provenance mismatch")
    metadata = read_json(package / "codex-package.json")
    require(metadata.get("version") == mapping["upstreamVersion"] and
            metadata.get("target") == mapping["target"] and
            metadata.get("entrypoint") == "bin/codex.exe", "Package metadata mismatch")


def sol_contract(source, upstream_commit):
    relative = "codex-rs/models-manager/models.json"
    upstream = json.loads(git(source, "show", f"{upstream_commit}:{relative}"))
    candidate = read_json(Path(source) / relative)
    def find(catalog):
        models = [m for m in catalog["models"] if m["slug"] == "gpt-6-sol"]
        require(len(models) == 1, "Missing or duplicate GPT-6 Sol catalog entry")
        return models[0]
    expected, actual = find(upstream), find(candidate)
    require(actual == expected, "Candidate changed the upstream GPT-6 Sol contract")
    return expected


def check_runtime_sol(models, expected):
    entries = [m for m in models if m.get("model") == "gpt-6-sol"]
    require(len(entries) == 1, "Runtime catalog does not recognize GPT-6 Sol")
    actual = entries[0]
    require(actual.get("defaultReasoningEffort") == expected["default_reasoning_level"],
            "Runtime Sol default effort mismatch")
    require([e["reasoningEffort"] for e in actual["supportedReasoningEfforts"]] ==
            [e["effort"] for e in expected["supported_reasoning_levels"]], "Runtime Sol effort contract mismatch")
    require(actual.get("defaultServiceTier") == expected["default_service_tier"], "Runtime Sol tier mismatch")
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mapping")
    parser.add_argument("--mode", choices=("build", "qualify", "record-build"), default="qualify")
    args = parser.parse_args()
    if args.mode == "record-build":
        record_build(args.mapping)
    else:
        print(json.dumps(load(args.mapping, args.mode)[0]))
