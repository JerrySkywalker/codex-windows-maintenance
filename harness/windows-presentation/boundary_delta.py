"""Incremental impact inventory; semantic dispositions require independent review."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from candidate_mapping import git, read_json, require, sha
from rolling_control import exact
from rolling_control import CONTROL

LAUNCH = re.compile(r"Command::new|\.spawn\(|\.status\(|\.output\(|CreateProcess|ShellExecute|creation_flags|CREATE_NO_WINDOW|CREATE_BREAKAWAY|JobObject")


def audit(source, donor, previous, upstream, matrix, mapping):
    for value in (donor, previous, upstream):
        exact(value)
    control = read_json(CONTROL)
    frozen, target = control["semanticDonor"], control["targetUpstream"]
    require((donor, previous, upstream) ==
            (frozen["commit"], frozen["upstreamCommit"], target["commit"]) and
            git(source, "show", "-s", "--format=%T", donor) == frozen["tree"],
            "Donor or target does not match reviewed rolling control")
    git(source, "merge-base", "--is-ancestor", previous, donor)
    # Release tags can live on separate release branches; compare exact trees.
    common = git(source, "merge-base", previous, upstream)
    require(mapping["candidateCommit"] == donor and mapping["upstreamCommit"] == previous,
            "Donor mapping identity mismatch")
    require(matrix["auditComplete"] and matrix["upstreamCommit"] == previous,
            "Complete prior semantic audit required")
    changed = set(git(source, "diff", "--name-only", "--no-renames", previous, upstream).splitlines())
    def blob(commit, path):
        values = git(source, "ls-tree", commit, "--", path).split()
        return values[2] if values else None
    files = []
    for item in mapping["files"]:
        path = item["path"]
        require(blob(donor, path) == item["candidateBlob"] and
                blob(previous, path) == item["upstreamBlob"], "Stale donor file mapping")
        files.append({"path": path, "matrixIds": item["matrixIds"], "donorBlob": item["candidateBlob"],
                      "previousUpstreamBlob": item["upstreamBlob"], "targetUpstreamBlob": blob(upstream, path),
                      "impact": "CHANGED" if path in changed else "UNAFFECTED"})
    ids = {name for item in files for name in item["matrixIds"]}
    require(len(files) == frozen["sourceFileCount"] and len(ids) == frozen["boundaryCount"],
            "Frozen 32-boundary / 35-file donor mapping required")
    require(ids <= {entry["id"] for entry in matrix["entries"]}, "Unknown mapped boundary")
    boundaries = []
    for entry in matrix["entries"]:
        touched = sorted(set(entry["paths"]) & changed)
        boundaries.append({**entry, "impact": "CHANGED" if touched else "UNAFFECTED",
                           "changedPaths": touched, "donorSourceDelta": entry["id"] in ids,
                           "decisionInherited": not touched})
    known = {path for entry in matrix["entries"] for path in entry["paths"]}
    patch = subprocess.check_output(["git", "-C", str(source), "diff", "--no-renames", "--unified=0",
                                     previous, upstream, "--", "codex-rs"]).decode(errors="replace")
    candidates, path = {}, None
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif path and line.startswith("+") and not line.startswith("+++") and LAUNCH.search(line[1:]):
            if path.endswith(".rs") and "/tests/" not in path and not path.endswith("_tests.rs"):
                candidates.setdefault(path, []).append(line[1:])
    return {"schemaVersion": 1, "status": "DELTA_REVIEW_REQUIRED", "donorCommit": donor,
            "previousUpstreamCommit": previous, "targetUpstreamCommit": upstream, "upstreamMergeBase": common,
            "changedPathCount": len(changed), "changedPaths": sorted(changed),
            "mappedFileCount": len(files), "mappedBoundaryCount": len(ids),
            "files": files, "boundaries": boundaries,
            "launchDeltaCandidates": [{"path": path, "impact": "CHANGED" if path in known else "NEW",
                                        "addedLines": lines} for path, lines in sorted(candidates.items())],
            "upstreamDiffSha256": hashlib.sha256(patch.encode()).hexdigest(),
            "qualificationInherited": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--donor", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.output.is_absolute() and not args.output.exists() and
            args.source.resolve() not in args.output.resolve().parents, "Fresh external delta evidence required")
    report = audit(args.source, args.donor, args.previous, args.upstream,
                   read_json(args.matrix), read_json(args.mapping))
    control = read_json(CONTROL)["semanticDonor"]
    require((sha(args.mapping), sha(args.matrix)) ==
            (control["sourceMappingSha256"], control["portMatrixSha256"]) and
            read_json(args.mapping)["matrixSha256"] == sha(args.matrix), "Frozen donor evidence hash mismatch")
    report.update(matrixSha256=sha(args.matrix), sourceMappingSha256=sha(args.mapping))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"Delta: {report['changedPathCount']} paths; {report['mappedBoundaryCount']} boundaries / {report['mappedFileCount']} files")


if __name__ == "__main__":
    main()
