# scripts/check_version.py

import subprocess
import sys
import tomllib

from packaging.version import Version


def current_version() -> Version:
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    return Version(data["project"]["version"])


def main_version() -> Version:
    contents = subprocess.check_output(
        ["git", "show", "origin/main:pyproject.toml"],
        text=True,
    )

    # tomllib.loads expects str
    data = tomllib.loads(contents)

    return Version(data["project"]["version"])


current = current_version()
main = main_version()

print(f"Version in PR:   {current}")
print(f"Version in main: {main}")

if current <= main:
    print(
        f"ERROR: version must be greater than main "
        f"({current} <= {main})",
        file=sys.stderr,
    )
    sys.exit(1)

print("Version is valid.")