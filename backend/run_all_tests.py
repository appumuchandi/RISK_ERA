#!/usr/bin/env python
import subprocess
import sys
import os

os.chdir(r"E:\PROJECTS\RISK-ERA\backend")
result = subprocess.run(
    [".venv\\Scripts\\python", "-m", "pytest", "tests/", "-x", "-v"],
    capture_output=True,
    text=True,
    cwd=r"E:\PROJECTS\RISK-ERA\backend"
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)