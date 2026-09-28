"""Interactive-desktop fixture validation, outside any Codex product state."""
import argparse
from pathlib import Path
from candidate_mapping import read_json, require, write_json
from qualify_candidate import isolated_environment, lifetime_fixture, observer, positive_control, wait


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pwsh", required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    require(not root.exists(), "Fixture output already exists")
    root.mkdir(parents=True)
    environment = isolated_environment(root)
    lifetime_fixture(root / "lifetime", environment)
    positive_control(args.pwsh, root / "positive-control", environment)
    for name, seconds, stopped in (("stop-handshake", 30, True), ("hard-deadline", 1, False)):
        phase = root / name
        phase.mkdir()
        marker = phase / "stop"
        watching, _ = observer(args.pwsh, phase, environment, seconds, marker)
        if stopped:
            require(watching.poll() is None, "Fixture observer ended before explicit stop")
            marker.write_text("STOP", encoding="ascii")
        wait(watching, 15)
        require(read_json(Path(str(marker) + ".done.json"))["stopMarkerObserved"] is stopped,
                "Observer stop/deadline acknowledgment mismatch")
    write_json(root / "validation.json", {"status": "WINDOWS_FIXTURE_VALIDATION_PASS",
        "nativeLifetimeCases": 3, "residualMembershipRejected": True,
        "positiveControl": "PASS", "observerStopHandshake": "PASS", "hardDeadlineRejected": "PASS",
        "productDaemonExecuted": False})
