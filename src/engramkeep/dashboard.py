"""Hardened local web dashboard for Engramkeep.

The dashboard binds to ``127.0.0.1`` only, requires a per-session token for
every API call, enforces the same path jail as the CLI, renders card content as
text-only DOM nodes, and sends a strict Content-Security-Policy. Mutations are
POST-only, require an explicit confirmation flag, and are disabled unless the
server is started with ``--allow-write``.
"""

from __future__ import annotations

import argparse
import hmac
import json
import secrets
import socket
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, unquote, urlsplit

from .config import resolve_home
from .dashboard_assets import load_asset
from .errors import EngramkeepError, StoreError, ValidationError
from .search import search_cards
from .store import Store

DEFAULT_PORT = 8765
MAX_BODY_BYTES = 65_536
MAX_QUERY_CHARS = 2_000
MAX_TAGS = 20
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
TOKEN_HEADER = "X-Engramkeep-Token"  # noqa: S105 - header name, not a secret
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)

LOGO_SVG = load_asset("logo.svg")
INDEX_HTML = load_asset("index.html")
APP_JS = load_asset("app.js")
STYLE_CSS = load_asset("style.css")


def status() -> dict[str, str]:
    """Return machine-readable dashboard status."""
    return {
        "component": "dashboard",
        "status": "available",
        "bind": "127.0.0.1",
        "auth": "per-session token",
        "writes": "disabled unless --allow-write is passed",
        "csp": "strict",
    }


def _first(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    return values[0]


def _int_parameter(query: dict[str, list[str]], name: str, default: int) -> int:
    raw = _first(query, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"parameter {name!r} must be an integer") from exc
    if value < 1 or value > MAX_LIMIT:
        raise ValidationError(f"parameter {name!r} must be between 1 and {MAX_LIMIT}")
    return value


class DashboardServer(ThreadingHTTPServer):
    """A loopback-only HTTP server with a per-session token."""

    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        """Bind exclusively on Windows so another local process cannot hijack the port."""
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if sys.platform == "win32" and exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()

    def __init__(
        self,
        address: tuple[str, int],
        *,
        store: Store,
        token: str,
        allow_write: bool,
        stderr: TextIO,
    ) -> None:
        super().__init__(address, DashboardHandler)
        self.store = store
        self.token = token
        self.allow_write = allow_write
        self.stderr = stderr

    @property
    def port(self) -> int:
        """Return the actual bound port."""
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        """Return the browser URL with the token in the fragment."""
        return f"http://127.0.0.1:{self.port}/#token={self.token}"


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard shell, assets, and JSON API."""

    server: DashboardServer
    protocol_version = "HTTP/1.1"
    timeout = 10

    def version_string(self) -> str:
        """Do not advertise the Python or server version."""
        return "Engramkeep"

    def log_message(self, format: str, *args: object) -> None:
        """Log the method and path without query strings or headers."""
        path = urlsplit(self.path).path
        print(f"dashboard: {self.command} {path}", file=self.server.stderr, flush=True)

    def do_GET(self) -> None:
        """Serve the shell, static assets, or read-only API endpoints."""
        if not self._valid_host():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/app.js":
            self._send_asset(APP_JS, "text/javascript; charset=utf-8")
            return
        if path == "/style.css":
            self._send_asset(STYLE_CSS, "text/css; charset=utf-8")
            return
        if path in {"/logo.svg", "/favicon.svg"}:
            self._send_svg(LOGO_SVG)
            return
        if path.startswith("/api/"):
            if not self._authorized():
                return
            self._handle_get_api(path, parse_qs(parsed.query))
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        """Accept opt-in remember and fix mutations only."""
        path = urlsplit(self.path).path
        if path not in {"/api/remember", "/api/fixes"}:
            self._drain_body()
            if not self._valid_host():
                return
            if path.startswith("/api/"):
                if not self._authorized():
                    return
                self._send_method_not_allowed("GET")
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        # Read the body before any response so an early rejection does not
        # reset the connection on Windows.
        raw = self._read_body_bytes()
        if raw is None:
            return
        if not self._valid_host():
            return
        if not self._authorized():
            return
        if not self._valid_origin():
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json"},
            )
            return
        if not self.server.allow_write:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "writes are disabled; restart with --allow-write"},
            )
            return
        body = self._decode_json_body(raw)
        if body is None:
            return
        if body.get("confirm") is not True:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "explicit confirmation is required: set confirm to true"},
            )
            return

        if path == "/api/remember":
            self._handle_post_remember(body)
        else:
            self._handle_post_fix(body)

    def _handle_post_remember(self, body: dict[str, Any]) -> None:
        project = body.get("project")
        decision = body.get("decision")
        tags = body.get("tags", [])
        if not isinstance(project, str) or not project.strip() or len(project) > 128:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "project must be a non-empty string of at most 128 characters"},
            )
            return
        if not isinstance(decision, str) or not decision.strip() or len(decision) > 4_000:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "decision must be a non-empty string of at most 4000 characters"},
            )
            return
        if not isinstance(tags, list) or len(tags) > MAX_TAGS:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"tags must be an array of at most {MAX_TAGS} strings"},
            )
            return
        if any(not isinstance(tag, str) or len(tag) > 64 for tag in tags):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "each tag must be a string of at most 64 characters"},
            )
            return

        try:
            result = self.server.store.remember(project, decision, tags=tags)
        except EngramkeepError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._log_internal_error(exc)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})
            return
        self._send_json(HTTPStatus.OK, result.to_dict())

    def _handle_post_fix(self, body: dict[str, Any]) -> None:
        error_text = body.get("error")
        solution = body.get("solution")
        project = body.get("project")
        workspace = body.get("workspace")
        if not isinstance(error_text, str) or not error_text.strip() or len(error_text) > 1_000:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "error must be a non-empty string of at most 1000 characters"},
            )
            return
        if not isinstance(solution, str) or not solution.strip() or len(solution) > 2_000:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "solution must be a non-empty string of at most 2000 characters"},
            )
            return
        if project is not None and (not isinstance(project, str) or len(project) > 128):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "project must be a string of at most 128 characters"},
            )
            return
        if workspace is not None and (not isinstance(workspace, str) or len(workspace) > 260):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "workspace must be a string of at most 260 characters"},
            )
            return

        try:
            entry, added = self.server.store.record_fix_result(
                error_text,
                solution,
                project=project,
                workspace=workspace,
            )
        except EngramkeepError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._log_internal_error(exc)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})
            return
        self._send_json(HTTPStatus.OK, {"fix": entry.to_dict(), "added": added})

    def do_OPTIONS(self) -> None:
        """Reject preflight requests; the dashboard has no CORS surface."""
        if not self._valid_host():
            return
        self._send_method_not_allowed("GET, POST")

    def do_PUT(self) -> None:
        """Reject unsupported mutations."""
        if not self._valid_host():
            return
        self._send_method_not_allowed("GET, POST")

    def do_PATCH(self) -> None:
        """Reject unsupported mutations."""
        if not self._valid_host():
            return
        self._send_method_not_allowed("GET, POST")

    def do_DELETE(self) -> None:
        """Reject unsupported mutations."""
        if not self._valid_host():
            return
        self._send_method_not_allowed("GET, POST")

    def _handle_get_api(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {"status": "ok", "writes": self.server.allow_write},
                )
                return
            if path == "/api/cards":
                self._send_projects()
                return
            if path.startswith("/api/cards/"):
                self._send_card(unquote(path[len("/api/cards/") :]))
                return
            if path == "/api/search":
                self._send_search(query)
                return
            if path == "/api/fixes":
                self._send_fixes(query)
                return
            if path == "/api/recent":
                limit = _int_parameter(query, "limit", DEFAULT_LIMIT)
                self._send_json(HTTPStatus.OK, {"entries": self.server.store.recent(limit)})
                return
            if path == "/api/doctor":
                self._send_json(
                    HTTPStatus.OK,
                    {"report": self.server.store.doctor().to_dict()},
                )
                return
            if path == "/api/export":
                self._send_json(HTTPStatus.OK, self.server.store.export_cards())
                return
            if path == "/api/remember":
                self._send_method_not_allowed("POST")
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except EngramkeepError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._log_internal_error(exc)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})

    def _send_projects(self) -> None:
        scan = self.server.store.scan_cards()
        cards = sorted(
            scan.cards,
            key=lambda card: (card.updated, card.title.lower()),
            reverse=True,
        )
        self._send_json(
            HTTPStatus.OK,
            {
                "projects": [
                    {
                        "id": card.id,
                        "title": card.title,
                        "tags": list(card.tags),
                        "updated": card.updated,
                    }
                    for card in cards
                ],
                "errors": list(scan.errors),
            },
        )

    def _send_card(self, project: str) -> None:
        card = self.server.store.get_card(project)
        if card is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": f"project not found: {project}"},
            )
            return
        self._send_json(HTTPStatus.OK, {"card": card.to_dict()})

    def _send_search(self, query: dict[str, list[str]]) -> None:
        text = _first(query, "q")
        if not text:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "missing query parameter: q"},
            )
            return
        if len(text) > MAX_QUERY_CHARS:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "query parameter 'q' is too long"},
            )
            return
        tag = _first(query, "tag") or None
        if tag is not None and len(tag) > 64:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "query parameter 'tag' is too long"},
            )
            return
        limit = _int_parameter(query, "limit", DEFAULT_LIMIT)
        scan = self.server.store.scan_cards()
        hits = search_cards(scan.cards, text, tag=tag, limit=limit)
        self._send_json(
            HTTPStatus.OK,
            {"hits": [hit.to_dict() for hit in hits], "errors": list(scan.errors)},
        )

    def _send_fixes(self, query: dict[str, list[str]]) -> None:
        text = _first(query, "q")
        if text is not None and len(text) > MAX_QUERY_CHARS:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "query parameter 'q' is too long"},
            )
            return
        limit = _int_parameter(query, "limit", DEFAULT_LIMIT)
        hits = self.server.store.search_fixes(text or None, limit=limit)
        self._send_json(
            HTTPStatus.OK,
            {"fixes": [hit.to_dict() for hit in hits]},
        )

    def _body_length(self) -> int | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._send_json(
                HTTPStatus.LENGTH_REQUIRED,
                {"error": "Content-Length is required"},
            )
            return None
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid Content-Length"},
            )
            return None
        if length < 0:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid Content-Length"},
            )
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "request body is too large"},
            )
            return None
        return length

    def _read_body_bytes(self) -> bytes | None:
        length = self._body_length()
        if length is None:
            return None
        data = self.rfile.read(length)
        if len(data) != length:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "incomplete request body"},
            )
            return None
        return data

    def _decode_json_body(self, data: bytes) -> dict[str, Any] | None:
        try:
            body = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "request body must be valid UTF-8 JSON"},
            )
            return None
        if not isinstance(body, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "request body must be a JSON object"},
            )
            return None
        return body

    def _drain_body(self) -> None:
        """Consume a small request body so an early rejection does not reset the socket."""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return
        try:
            length = int(raw_length)
        except ValueError:
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            return
        try:
            self.rfile.read(length)
        except OSError:
            pass

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "").strip().lower()
        port = self.server.port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update({"127.0.0.1", "localhost"})
        if host not in allowed:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "invalid Host header"},
            )
            return False
        return True

    def _authorized(self) -> bool:
        supplied = self.headers.get(TOKEN_HEADER, "")
        if not supplied or not hmac.compare_digest(
            supplied.encode("utf-8"), self.server.token.encode("utf-8")
        ):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"error": "missing or invalid dashboard token"},
                extra_headers={"WWW-Authenticate": "EngramkeepToken"},
            )
            return False
        return True

    def _valid_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        port = self.server.port
        allowed = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
        if origin.rstrip("/") not in allowed:
            self._send_json(
                HTTPStatus.FORBIDDEN,
                {"error": "cross-origin request rejected"},
            )
            return False
        return True

    def _send_html(self, html: str) -> None:
        self._send_bytes(
            HTTPStatus.OK,
            html.encode("utf-8"),
            "text/html; charset=utf-8",
            extra_headers={"Content-Security-Policy": CSP},
        )

    def _send_asset(self, text: str, content_type: str) -> None:
        self._send_bytes(HTTPStatus.OK, text.encode("utf-8"), content_type)

    def _send_svg(self, svg: str) -> None:
        self._send_bytes(
            HTTPStatus.OK,
            svg.encode("utf-8"),
            "image/svg+xml; charset=utf-8",
            extra_headers={"Content-Security-Policy": "default-src 'none'"},
        )

    def _send_json(
        self,
        status: int | HTTPStatus,
        payload: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(
            status,
            data,
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def _send_bytes(
        self,
        status: int | HTTPStatus,
        data: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Connection", "close")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def _send_method_not_allowed(self, allow: str) -> None:
        self._send_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "method not allowed"},
            extra_headers={"Allow": allow},
        )

    def _log_internal_error(self, exc: Exception) -> None:
        print(
            f"dashboard: internal error: {type(exc).__name__}: {exc}",
            file=self.server.stderr,
            flush=True,
        )


def create_server(
    home: Path | str,
    *,
    port: int = DEFAULT_PORT,
    allow_write: bool = False,
    token: str | None = None,
    stderr: TextIO | None = None,
) -> DashboardServer:
    """Create a loopback-only dashboard server without starting it."""
    if not 0 <= port <= 65_535:
        raise StoreError("port must be between 0 and 65535")
    store = Store(home)
    store.require_initialized()
    session_token = token if token is not None else secrets.token_urlsafe(32)
    if not session_token:
        raise StoreError("dashboard token must not be empty")
    return DashboardServer(
        ("127.0.0.1", port),
        store=store,
        token=session_token,
        allow_write=allow_write,
        stderr=stderr if stderr is not None else sys.stderr,
    )


def serve(
    home: Path | str | None = None,
    *,
    port: int = DEFAULT_PORT,
    allow_write: bool = False,
    open_browser: bool = False,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the dashboard until interrupted."""
    server = create_server(
        home if home is not None else resolve_home(),
        port=port,
        allow_write=allow_write,
        stderr=stderr,
    )
    out = stdout if stdout is not None else sys.stdout
    print("Engramkeep dashboard", file=out)
    print(f"Bind: http://127.0.0.1:{server.port}", file=out)
    print(f"Open: {server.url}", file=out)
    print(
        f"Writes: {'enabled' if allow_write else 'disabled (pass --allow-write to enable)'}",
        file=out,
    )
    if open_browser:
        webbrowser.open(server.url)
    print("Press Ctrl+C to stop.", file=out, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.", file=out, flush=True)
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the standalone dashboard entry point."""
    parser = argparse.ArgumentParser(
        prog="engramkeep-dashboard",
        description="Engramkeep local dashboard.",
    )
    parser.add_argument("--home", metavar="DIR", help="memory directory")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"loopback port (default: {DEFAULT_PORT}; 0 picks a free port)",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="enable the remember and fix forms",
    )
    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="open the dashboard URL in the default browser",
    )
    args = parser.parse_args(argv)
    try:
        return serve(
            resolve_home(args.home),
            port=args.port,
            allow_write=args.allow_write,
            open_browser=args.open_browser,
        )
    except EngramkeepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
