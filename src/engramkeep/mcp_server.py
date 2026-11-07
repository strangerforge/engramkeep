"""MCP server placeholder.

The 0.2.0 implementation will speak newline-delimited JSON over stdio using
the MCP protocol version 2025-11-25. It will not reuse the legacy
Content-Length framing prototype, and it will not open a network listener.
"""

from __future__ import annotations

import sys

MCP_PROTOCOL_VERSION = "2025-11-25"
STATUS = "not implemented in 0.1.0; planned for 0.2.0"


def status() -> dict[str, str]:
    """Return machine-readable stub status."""
    return {
        "component": "mcp",
        "status": STATUS,
        "transport": "stdio",
        "protocol_version": MCP_PROTOCOL_VERSION,
    }


def main() -> int:
    """Explain that the MCP server is not available yet."""
    print(
        "Engramkeep MCP server is not implemented in 0.1.0. "
        "It is planned for 0.2.0 with stdio newline-delimited JSON.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
