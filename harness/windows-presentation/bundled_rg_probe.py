"""Bounded stdin probe keeps the exact bundled helper observable, without model credentials."""
import subprocess
import sys
import time
from pathlib import Path

executable = Path(sys.argv[1]).resolve(strict=True)
process = subprocess.Popen([str(executable), "--no-config", "--color", "never", "--fixed-strings", "rg-probe-ok", "-"],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=subprocess.CREATE_NO_WINDOW)
try:
    time.sleep(2)  # Keep the owned helper alive long enough for exact-handle observation.
    output, error = process.communicate(b"rg-probe-ok\n", timeout=5)
    if process.returncode != 0 or output.strip() != b"rg-probe-ok":
        raise RuntimeError("Bundled rg probe failed")
    print(str(executable))
    print(output.decode().strip())
finally:
    if process.poll() is None:
        process.kill()
        process.wait(5)
