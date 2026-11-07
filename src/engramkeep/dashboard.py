"""Web dashboard placeholder.

The 0.2.0 implementation will bind to loopback only, require a per-session
token, enforce a path jail, use a strict Content-Security-Policy, render card
content as text rather than HTML, and require an explicit POST plus
confirmation for mutations.
"""

from __future__ import annotations

import sys

STATUS = "not implemented in 0.1.0; planned for 0.2.0"


def status() -> dict[str, str]:
    """Return machine-readable stub status."""
    return {
        "component": "dashboard",
        "status": STATUS,
        "bind": "127.0.0.1",
        "writes": "explicit confirmation required",
    }


def main() -> int:
    """Explain that the dashboard is not available yet."""
    print(
        "Engramkeep dashboard is not implemented in 0.1.0. "
        "It is planned for 0.2.0 with localhost-only binding and a token.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
