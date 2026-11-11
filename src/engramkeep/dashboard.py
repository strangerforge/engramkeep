"""Hardened local web dashboard for Engramkeep.

The dashboard binds to ``127.0.0.1`` only, requires a per-session token for
every API call, enforces the same path jail as the CLI, renders card content as
text, and sends a strict Content-Security-Policy. Mutations are POST-only,
require an explicit confirmation flag, and are disabled unless the server is
started with ``--allow-write``.
"""

from __future__ import annotations

import argparse
import hmac
import json
import secrets
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, unquote, urlsplit

from .config import resolve_home
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
        """Accept the opt-in remember mutation only."""
        path = urlsplit(self.path).path
        if path != "/api/remember":
            self._drain_body()
            if not self._valid_host():
                return
            if path.startswith("/api/"):
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
        if not supplied or not hmac.compare_digest(supplied, self.server.token):
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
        help="enable the remember form",
    )
    args = parser.parse_args(argv)
    try:
        return serve(
            resolve_home(args.home),
            port=args.port,
            allow_write=args.allow_write,
        )
    except EngramkeepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <title>Engramkeep</title>
  <rect width="512" height="512" fill="#f3e9d7"/>
  <g stroke="#221c15" stroke-width="18" stroke-linecap="round" fill="none">
    <path d="M277 255 A75 75 0 1 0 259.5 303.2"/>
    <line x1="127" y1="255" x2="277" y2="255"/>
    <line x1="322" y1="150" x2="322" y2="330"/>
    <line x1="322" y1="258" x2="384" y2="182"/>
  </g>
  <line x1="322" y1="258" x2="386" y2="330" stroke="#c2543a"
        stroke-width="18" stroke-linecap="round"/>
</svg>
"""


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>Engramkeep</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="stylesheet" href="/style.css">
  <script src="/app.js" defer></script>
</head>
<body>
  <header>
    <div class="brand">
      <img class="brand-logo" src="/logo.svg" width="44" height="44" alt="">
      <div>
        <h1>Engramkeep</h1>
        <p class="muted">Local-first project memory, served from 127.0.0.1.</p>
      </div>
    </div>
    <p id="status" role="status" aria-live="polite">Loading...</p>
  </header>
  <main>
    <section aria-labelledby="search-heading">
      <h2 id="search-heading">Search</h2>
      <form id="search-form">
        <label for="search-query">Query</label>
        <input id="search-query" name="q" type="search" required maxlength="2000"
               autocomplete="off">
        <label for="search-tag">Tag (optional)</label>
        <input id="search-tag" name="tag" type="text" maxlength="64" autocomplete="off">
        <button type="submit">Search</button>
      </form>
      <ul id="search-results" class="results"></ul>
    </section>
    <section aria-labelledby="projects-heading">
      <h2 id="projects-heading">Projects</h2>
      <ul id="project-list" class="results"></ul>
    </section>
    <section aria-labelledby="card-heading">
      <h2 id="card-heading">Card</h2>
      <div id="card-view" class="card"><p class="muted">Select a project.</p></div>
    </section>
    <section aria-labelledby="recent-heading">
      <h2 id="recent-heading">Recent activity</h2>
      <ul id="recent-list" class="results"></ul>
    </section>
    <section aria-labelledby="fixes-heading">
      <h2 id="fixes-heading">Troubleshooting fixes</h2>
      <form id="fixes-form">
        <label for="fixes-query">Filter fixes (optional)</label>
        <input id="fixes-query" name="q" type="search" maxlength="2000" autocomplete="off">
        <button type="submit">Filter</button>
      </form>
      <ul id="fixes-list" class="results"></ul>
    </section>
    <section aria-labelledby="doctor-heading">
      <h2 id="doctor-heading">Doctor</h2>
      <pre id="doctor-view" class="pre"></pre>
    </section>
    <section id="remember-section" aria-labelledby="remember-heading" hidden>
      <h2 id="remember-heading">Remember a decision</h2>
      <form id="remember-form">
        <label for="remember-project">Project</label>
        <input id="remember-project" name="project" type="text" required maxlength="128"
               autocomplete="off">
        <label for="remember-decision">Decision</label>
        <textarea id="remember-decision" name="decision" required maxlength="4000"
                  rows="5"></textarea>
        <label for="remember-tags">Tags (comma-separated)</label>
        <input id="remember-tags" name="tags" type="text" maxlength="400" autocomplete="off">
        <label class="checkbox">
          <input id="remember-confirm" type="checkbox" required>
          I confirm this is a durable decision.
        </label>
        <button type="submit">Remember</button>
      </form>
    </section>
  </main>
  <noscript><p>Engramkeep dashboard requires JavaScript.</p></noscript>
</body>
</html>
"""


APP_JS = """(() => {
  "use strict";

  const TOKEN_KEY = "engramkeep-dashboard-token";
  const state = { token: null, writes: false };

  function storageGet(key) {
    try {
      return sessionStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch (error) {
      // The token still works for this page load.
    }
  }

  function readToken() {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const fromHash = hash.get("token");
    if (fromHash) {
      storageSet(TOKEN_KEY, fromHash);
      try {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      } catch (error) {
        // Keep the fragment when the browser refuses to rewrite history.
      }
      return fromHash;
    }
    return storageGet(TOKEN_KEY);
  }

  function setStatus(message, isError = false) {
    const node = document.getElementById("status");
    node.textContent = message;
    node.classList.toggle("error", isError);
  }

  async function api(path, options = {}) {
    if (!state.token) {
      throw new Error("No dashboard token. Open the URL printed by engramkeep dashboard.");
    }
    const headers = new Headers(options.headers || {});
    headers.set("X-Engramkeep-Token", state.token);
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, { ...options, headers, cache: "no-store" });
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // Keep the status text when the body is not JSON.
    }
    if (!response.ok) {
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) {
      node.className = className;
    }
    return node;
  }

  function renderProjects(projects) {
    const list = document.getElementById("project-list");
    clear(list);
    if (!projects.length) {
      list.appendChild(text("li", "No projects yet.", "muted"));
      return;
    }
    for (const project of projects) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = project.title;
      button.addEventListener("click", () => loadCard(project.id));
      item.appendChild(button);
      item.appendChild(text("span", ` ${project.id}`, "muted"));
      if (project.tags.length) {
        item.appendChild(text("span", ` [${project.tags.join(", ")}]`, "muted"));
      }
      list.appendChild(item);
    }
  }

  function renderSearch(hits) {
    const list = document.getElementById("search-results");
    clear(list);
    if (!hits.length) {
      list.appendChild(text("li", "No matches.", "muted"));
      return;
    }
    for (const hit of hits) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = hit.title;
      button.addEventListener("click", () => loadCard(hit.id));
      item.appendChild(button);
      item.appendChild(text("span", ` ${hit.id}`, "muted"));
      if (hit.snippet) {
        item.appendChild(text("p", hit.snippet, "snippet"));
      }
      list.appendChild(item);
    }
  }

  function renderCard(card) {
    const view = document.getElementById("card-view");
    clear(view);
    view.appendChild(text("h3", card.title));
    view.appendChild(text("p", `id: ${card.id}`, "muted"));
    if (card.tags.length) {
      view.appendChild(text("p", `tags: ${card.tags.join(", ")}`, "muted"));
    }
    view.appendChild(text("p", `updated: ${card.updated}`, "muted"));
    view.appendChild(text("pre", card.body, "pre"));
  }

  function renderRecent(entries) {
    const list = document.getElementById("recent-list");
    clear(list);
    if (!entries.length) {
      list.appendChild(text("li", "No activity yet.", "muted"));
      return;
    }
    for (const entry of entries) {
      list.appendChild(text("li", entry));
    }
  }

  function renderFixes(fixes) {
    const list = document.getElementById("fixes-list");
    clear(list);
    if (!fixes.length) {
      list.appendChild(text("li", "No fixes recorded yet.", "muted"));
      return;
    }
    for (const hit of fixes) {
      const item = document.createElement("li");
      item.appendChild(text("strong", `${hit.project} (${hit.date})`));
      item.appendChild(text("span", ` ${hit.workspace || "General"}`, "muted"));
      item.appendChild(text("p", `problem: ${hit.error}`, "snippet"));
      item.appendChild(text("p", `fix: ${hit.fix}`, "snippet"));
      list.appendChild(item);
    }
  }

  function renderDoctor(report) {
    document.getElementById("doctor-view").textContent = JSON.stringify(report, null, 2);
  }

  async function loadProjects() {
    const data = await api("/api/cards");
    renderProjects(data.projects);
  }

  async function loadCard(id) {
    const data = await api(`/api/cards/${encodeURIComponent(id)}`);
    renderCard(data.card);
  }

  async function loadRecent() {
    const data = await api("/api/recent?limit=10");
    renderRecent(data.entries);
  }

  async function loadFixes(query = "") {
    const params = new URLSearchParams({ limit: "10" });
    if (query) {
      params.set("q", query);
    }
    const data = await api(`/api/fixes?${params.toString()}`);
    renderFixes(data.fixes);
  }

  async function loadDoctor() {
    const data = await api("/api/doctor");
    renderDoctor(data.report);
  }

  async function refresh() {
    setStatus("Loading...");
    try {
      const health = await api("/api/health");
      state.writes = Boolean(health.writes);
      document.getElementById("remember-section").hidden = !state.writes;
      await Promise.all([loadProjects(), loadRecent(), loadFixes(), loadDoctor()]);
      setStatus(state.writes ? "Ready. Writes are enabled." : "Ready. Read-only mode.");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  document.getElementById("search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("search-query").value.trim();
    const tag = document.getElementById("search-tag").value.trim();
    if (!query) {
      setStatus("Enter a search query.", true);
      return;
    }
    const params = new URLSearchParams({ q: query });
    if (tag) {
      params.set("tag", tag);
    }
    try {
      setStatus("Searching...");
      const data = await api(`/api/search?${params.toString()}`);
      renderSearch(data.hits);
      setStatus(`${data.hits.length} result(s).`);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("fixes-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("fixes-query").value.trim();
    try {
      setStatus("Loading fixes...");
      await loadFixes(query);
      setStatus("Ready.");
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("remember-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.writes) {
      setStatus("Writes are disabled.", true);
      return;
    }
    if (!document.getElementById("remember-confirm").checked) {
      setStatus("Confirm the decision before saving.", true);
      return;
    }
    const project = document.getElementById("remember-project").value.trim();
    const decision = document.getElementById("remember-decision").value.trim();
    const tags = document.getElementById("remember-tags").value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (!project || !decision) {
      setStatus("Project and decision are required.", true);
      return;
    }
    try {
      setStatus("Saving...");
      await api("/api/remember", {
        method: "POST",
        body: JSON.stringify({ project, decision, tags, confirm: true }),
      });
      document.getElementById("remember-form").reset();
      setStatus("Decision remembered.");
      await Promise.all([loadProjects(), loadRecent(), loadDoctor()]);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  state.token = readToken();
  if (!state.token) {
    setStatus("No dashboard token. Open the URL printed by engramkeep dashboard.", true);
  } else {
    refresh();
  }
})();
"""


STYLE_CSS = """\
:root {
  color-scheme: light dark;
  --bg: #f7f7f5;
  --panel: #ffffff;
  --text: #1f2328;
  --muted: #5b6570;
  --border: #d8dde3;
  --accent: #1f6feb;
  --error: #b42318;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111418;
    --panel: #171b21;
    --text: #e6edf3;
    --muted: #9aa7b4;
    --border: #2d333b;
    --accent: #6cb6ff;
    --error: #ff8a80;
  }
}

* {
  box-sizing: border-box;
}

body {
  margin: 0 auto;
  max-width: 70rem;
  padding: 1.5rem;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}

header {
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
}

.brand {
  align-items: center;
  display: flex;
  gap: 0.85rem;
}

.brand h1 {
  margin: 0;
}

.brand p {
  margin: 0.2rem 0 0;
}

.brand-logo {
  border: 1px solid var(--border);
  border-radius: 0.45rem;
  display: block;
  flex-shrink: 0;
}

h1, h2, h3 {
  line-height: 1.25;
}

main {
  display: grid;
  gap: 1.25rem;
  grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
}

section {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  padding: 1rem;
}

form {
  display: grid;
  gap: 0.5rem;
}

label {
  font-weight: 600;
}

input, textarea, button {
  font: inherit;
}

input, textarea {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 0.35rem;
  color: var(--text);
  padding: 0.5rem;
  width: 100%;
}

button {
  background: var(--accent);
  border: 0;
  border-radius: 0.35rem;
  color: #ffffff;
  cursor: pointer;
  padding: 0.5rem 0.8rem;
}

button:hover {
  filter: brightness(1.08);
}

.results {
  list-style: none;
  margin: 0.8rem 0 0;
  padding: 0;
}

.results li {
  border-top: 1px solid var(--border);
  padding: 0.5rem 0;
}

.results li:first-child {
  border-top: 0;
}

.muted {
  color: var(--muted);
}

.error {
  color: var(--error);
  font-weight: 600;
}

.snippet {
  color: var(--muted);
  margin: 0.25rem 0 0;
}

.card h3 {
  margin-top: 0;
}

.pre {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 0.35rem;
  overflow: auto;
  padding: 0.75rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.checkbox {
  align-items: center;
  display: flex;
  gap: 0.5rem;
}

.checkbox input {
  width: auto;
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
