import re
import subprocess
from pathlib import Path

PATTERNS = (
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def main() -> None:
    tracked = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    findings = []
    for name in tracked.decode().split("\0"):
        if not name:
            continue
        path = Path(name)
        if path.name == ".env" or path.suffix in {".log", ".db"}:
            findings.append(name)
        elif path.is_file() and any(pattern.search(path.read_bytes()) for pattern in PATTERNS):
            findings.append(name)
    if findings:
        print("Potential secret-bearing files:", ", ".join(findings))
        raise SystemExit(1)
    print("Tracked-file secret scan passed; no credential values were displayed.")


if __name__ == "__main__":
    main()
