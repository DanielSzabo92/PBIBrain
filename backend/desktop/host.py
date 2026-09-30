"""Windows desktop host for the local PBIBrain application."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from backend.api.app import BrainAPI, BrainApp
from backend.graph.repository import GraphRepository
from backend.native_runtime import configure_native_runtime
from backend.projects import PROJECT_VERSION, ProjectService


_IGNORED_SOURCE_DIRECTORIES = frozenset({".pbibrain", ".git", "node_modules"})
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DESKTOP_BOOT_TAG = b'<script src="/desktop/bootstrap.js"></script>'
_DESKTOP_BOOT_JAVASCRIPT = b"window.__PBIBRAIN_DESKTOP__=true;"
_CSP = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-src 'none'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'"
)


def discover_pbip_sources(folder: str | Path) -> list[Path]:
    """Find project sources without accidentally collecting nested backups.

    All PBIP files directly in the selected folder belong to the project. Only
    when none exist there do we recurse, excluding application, Git, and Node
    state directories.
    """

    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Project folder does not exist: {root}")

    top_level = sorted(
        (path.resolve() for path in root.iterdir() if path.is_file() and path.suffix.casefold() == ".pbip"),
        key=lambda path: str(path).casefold(),
    )
    if top_level:
        return top_level

    discovered: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            (name for name in directory_names if name.casefold() not in _IGNORED_SOURCE_DIRECTORIES),
            key=str.casefold,
        )
        current_path = Path(current)
        discovered.extend(
            (current_path / name).resolve()
            for name in file_names
            if Path(name).suffix.casefold() == ".pbip"
        )
    return sorted(discovered, key=lambda path: str(path).casefold())


def _relative_path(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class DesktopController:
    """pywebview JS API and owner of the active native project repository."""

    def __init__(
        self,
        *,
        static_dir: str | Path,
        repository_factory: Callable[[Path], GraphRepository] | None = None,
        project_service_factory: Callable[[Path], ProjectService] = ProjectService,
        runtime_configurer: Callable[[], Path | None] = configure_native_runtime,
        folder_picker: Callable[[], str | Path | None] | None = None,
        source_picker: Callable[[], list[str | Path] | tuple[str | Path, ...] | None] | None = None,
    ) -> None:
        self.static_dir = Path(static_dir).resolve()
        self._repository_factory = repository_factory or (lambda path: GraphRepository(path))
        self._project_service_factory = project_service_factory
        self._runtime_configurer = runtime_configurer
        self._folder_picker = folder_picker
        self._source_picker = source_picker
        self._lock = threading.RLock()
        self._application: BrainApp | None = None
        self._repository: GraphRepository | None = None
        self._project: dict[str, str] | None = None
        self._project_service: ProjectService | None = None
        self._marker_path: Path | None = None
        self._server_url: str | None = None
        self._session_id = uuid.uuid4().hex

    def attach_server(self, url: str) -> None:
        parsed = urlsplit(str(url))
        if parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS or parsed.username or parsed.password:
            raise ValueError("Desktop server must use a local HTTP URL")
        with self._lock:
            self._server_url = str(url).rstrip("/")

    def get_session(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "project": dict(self._project) if self._project is not None else None,
                "api_url": self._server_url,
            }

    def endpoint_session(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "project": dict(self._project) if self._project is not None else None,
                "session_id": self._session_id,
            }

    def choose_folder(self) -> dict[str, Any]:
        try:
            selected = self._pick_folder()
            if selected is None or str(selected).strip() == "":
                return {"ok": True, "folder": None}
            return {"ok": True, "folder": str(Path(selected).expanduser().resolve())}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def choose_sources(self) -> dict[str, Any]:
        try:
            selected = self._pick_sources()
            sources = [] if not selected else [str(Path(path).expanduser().resolve()) for path in selected]
            return {"ok": True, "sources": sources}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _pick_folder(self) -> str | Path | None:
        if self._folder_picker is not None:
            return self._folder_picker()
        import webview  # type: ignore[import-not-found]

        if not webview.windows:
            raise RuntimeError("The PBIBrain window is not ready")
        dialog_type = getattr(webview, "FOLDER_DIALOG", None)
        if dialog_type is None:
            dialog_type = getattr(getattr(webview, "FileDialog", object), "FOLDER", None)
        if dialog_type is None:
            raise RuntimeError("This desktop runtime does not support folder selection")
        result = webview.windows[0].create_file_dialog(dialog_type, allow_multiple=False)
        if not result:
            return None
        if isinstance(result, (tuple, list)):
            return result[0] if result else None
        return result

    def _pick_sources(self) -> list[str | Path] | tuple[str | Path, ...] | None:
        if self._source_picker is not None:
            return self._source_picker()
        import webview  # type: ignore[import-not-found]

        if not webview.windows:
            raise RuntimeError("The PBIBrain window is not ready")
        dialog_type = getattr(webview, "OPEN_DIALOG", None)
        if dialog_type is None:
            dialog_type = getattr(getattr(webview, "FileDialog", object), "OPEN", None)
        if dialog_type is None:
            raise RuntimeError("This desktop runtime does not support source selection")
        result = webview.windows[0].create_file_dialog(
            dialog_type,
            allow_multiple=True,
            file_types=("Power BI sources (*.pbip;*.json;*.bim)",),
        )
        if not result:
            return None
        if isinstance(result, (tuple, list)):
            return result
        return [result]

    def open_project(self, name: str, folder: str) -> dict[str, Any]:
        try:
            project_name = str(name).strip()
            if not project_name:
                raise ValueError("Project name is required")
            root = Path(folder).expanduser().resolve()
            if not root.is_dir():
                raise ValueError(f"Project folder does not exist: {root}")
            with self._lock:
                return self._open_project(project_name, root)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def add_sources(self, paths: list[str] | tuple[str, ...]) -> dict[str, Any]:
        try:
            if not isinstance(paths, (list, tuple)):
                raise ValueError("Source paths must be a list")
            with self._lock:
                if self._project_service is None or self._project is None:
                    raise ValueError("Open a project first")
                config = self._project_service.get_config()
                base = self._project_service.config_path.parent
                known = {
                    str((base / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()).casefold()
                    for value in config["sources"]
                }
                added: list[str] = []
                for raw_path in paths:
                    source = Path(str(raw_path)).expanduser().resolve()
                    if not source.is_file():
                        raise ValueError(f"Source file does not exist: {source}")
                    if source.suffix.casefold() not in {".pbip", ".json", ".bim"}:
                        raise ValueError(f"Unsupported source file: {source.name}")
                    key = str(source).casefold()
                    if key in known:
                        continue
                    relative = _relative_path(source, base)
                    config["sources"].append(relative)
                    added.append(relative)
                    known.add(key)
                saved = self._project_service.save_config(config)
                return {
                    "ok": True,
                    "project": dict(self._project),
                    "sources": list(saved["sources"]),
                    "added": added,
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _open_project(self, name: str, root: Path) -> dict[str, Any]:
        config_path = root / ".pbibrain" / "brain.json"
        if self._project is not None and Path(self._project["config_path"]) == config_path.resolve():
            return self._open_result(source_count=len(self._project_service_factory(config_path).get_config()["sources"]))

        service = self._project_service_factory(config_path)
        if config_path.is_file():
            config = service.get_config()
        else:
            sources = discover_pbip_sources(root)
            config = service.save_config(
                {
                    "version": PROJECT_VERSION,
                    "name": name,
                    "sources": [_relative_path(source, config_path.parent) for source in sources],
                    "database": "brain.lbug",
                    "identity_map": "identity-map.json",
                }
            )

        self._runtime_configurer()
        paths = service.paths()
        new_repository = self._repository_factory(paths["database"])
        new_application: BrainApp | None = None
        new_marker = config_path.parent / "connection.json"
        new_session_id = uuid.uuid4().hex
        project = {
            "name": str(config["name"]),
            "folder": str(root),
            "config_path": str(config_path.resolve()),
        }
        try:
            new_application = BrainApp(
                BrainAPI(new_repository, overrides_path=paths["overrides"]),
                project=service,
                static_dir=self.static_dir,
            )
            if self._server_url is None:
                raise RuntimeError("Desktop server is not ready")
            _write_json_atomic(
                new_marker,
                {
                    "url": self._server_url,
                    "config_path": project["config_path"],
                    "session_id": new_session_id,
                },
            )
        except BaseException:
            if new_application is not None:
                new_application.close()
            new_repository.close()
            raise

        old_application = self._application
        old_repository = self._repository
        old_marker = self._marker_path
        old_session_id = self._session_id
        self._application = new_application
        self._repository = new_repository
        self._project = project
        self._project_service = service
        self._marker_path = new_marker
        if old_marker is not None and old_marker != new_marker:
            self._remove_owned_marker(old_marker, session_id=old_session_id)
        self._session_id = new_session_id
        if old_application is not None:
            old_application.close()
        if old_repository is not None:
            old_repository.close()
        return self._open_result(source_count=len(config["sources"]))

    def _open_result(self, *, source_count: int) -> dict[str, Any]:
        session = self.get_session()
        session["source_count"] = source_count
        return session

    def close_project(self) -> dict[str, Any]:
        try:
            with self._lock:
                self._close_project()
                return self.get_session()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _close_project(self) -> None:
        application, repository, marker = self._application, self._repository, self._marker_path
        self._application = None
        self._repository = None
        self._project = None
        self._project_service = None
        self._marker_path = None
        if marker is not None:
            self._remove_owned_marker(marker)
        if application is not None:
            application.close()
        if repository is not None:
            repository.close()

    def _remove_owned_marker(self, marker: Path, *, session_id: str | None = None) -> None:
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping) and payload.get("session_id") == (session_id or self._session_id):
                marker.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            pass

    def shutdown(self) -> None:
        with self._lock:
            self._close_project()

    def active_application(self) -> BrainApp | None:
        return self._application


class DesktopApplication:
    """Persistent same-origin WSGI surface for onboarding and project APIs."""

    def __init__(self, controller: DesktopController) -> None:
        self.controller = controller
        self.static_dir = controller.static_dir

    def __call__(self, environ: Mapping[str, Any], start_response: Any) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        host = str(environ.get("HTTP_HOST") or "127.0.0.1")
        origin = str(environ.get("HTTP_ORIGIN") or "")
        try:
            self._validate_request(host, origin)
            if path.rstrip("/") == "/desktop/session":
                if method != "GET":
                    return self._json(start_response, 405, {"ok": False, "error": "method not allowed"})
                return self._json(start_response, 200, self.controller.endpoint_session())
            if path == "/desktop/bootstrap.js":
                if method != "GET":
                    return self._json(start_response, 405, {"ok": False, "error": "method not allowed"})
                return self._bootstrap(start_response)
            if path == "/api" or path.startswith("/api/"):
                with self.controller._lock:
                    application = self.controller.active_application()
                    if application is None:
                        return self._json(start_response, 503, {"error": "Open a project first"})
                    requested_session = str(environ.get("HTTP_X_PBIBRAIN_SESSION") or "")
                    if requested_session and requested_session != self.controller._session_id:
                        return self._json(start_response, 409, {"error": "Desktop session changed; reopen the project connection"})
                    return application(environ, start_response)
            if method != "GET":
                return self._json(start_response, 405, {"ok": False, "error": "method not allowed"})
            return self._static(path, start_response)
        except PermissionError as exc:
            return self._json(start_response, 403, {"ok": False, "error": str(exc)})
        except OSError as exc:
            return self._json(start_response, 404, {"ok": False, "error": str(exc)})

    @staticmethod
    def _validate_request(host: str, origin: str) -> None:
        parsed_host = urlsplit(f"http://{host}")
        if parsed_host.hostname not in _LOCAL_HOSTS or parsed_host.username or parsed_host.password or parsed_host.path:
            raise PermissionError("Only local requests are supported")
        if origin:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme != "http"
                or parsed_origin.hostname not in _LOCAL_HOSTS
                or parsed_origin.username
                or parsed_origin.password
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.port != parsed_host.port
            ):
                raise PermissionError("Origin is not allowed")

    def _static(self, path: str, start_response: Any) -> list[bytes]:
        relative = unquote(path).lstrip("/")
        asset = (self.static_dir / relative).resolve() if relative else self.static_dir / "index.html"
        if not asset.is_relative_to(self.static_dir):
            raise PermissionError("Path is not allowed")
        if not asset.is_file() and "." not in Path(relative).name:
            asset = self.static_dir / "index.html"
        if not asset.is_file():
            return self._json(start_response, 404, {"ok": False, "error": "asset not found"})
        raw = asset.read_bytes()
        if asset.name == "index.html":
            marker = b"<head>"
            raw = raw.replace(marker, marker + _DESKTOP_BOOT_TAG, 1) if marker in raw else _DESKTOP_BOOT_TAG + raw
        mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        headers = self._security_headers() + [
            ("Content-Type", mime),
            ("Content-Length", str(len(raw))),
            ("Cache-Control", "no-cache" if asset.name == "index.html" else "public, max-age=31536000, immutable"),
        ]
        start_response("200 OK", headers)
        return [raw]

    def _bootstrap(self, start_response: Any) -> list[bytes]:
        headers = self._security_headers() + [
            ("Content-Type", "application/javascript"),
            ("Content-Length", str(len(_DESKTOP_BOOT_JAVASCRIPT))),
            ("Cache-Control", "no-store"),
        ]
        start_response("200 OK", headers)
        return [_DESKTOP_BOOT_JAVASCRIPT]

    def _json(self, start_response: Any, status: int, payload: Mapping[str, Any]) -> list[bytes]:
        raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
        reason = {200: "OK", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 409: "Conflict", 503: "Service Unavailable"}.get(status, "Error")
        headers = self._security_headers() + [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(raw))),
            ("Cache-Control", "no-store"),
        ]
        start_response(f"{status} {reason}", headers)
        return [raw]

    @staticmethod
    def _security_headers() -> list[tuple[str, str]]:
        return [
            ("Content-Security-Policy", _CSP),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ]


class DesktopServer:
    """One serialized loopback server shared by onboarding and the open project."""

    def __init__(self, controller: DesktopController, *, host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("PBIBrain desktop is local-only")
        self.controller = controller
        self.application = DesktopApplication(controller)
        self._server: WSGIServer = make_server(host, int(port), self.application)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self.controller.attach_server(self.url)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._server.serve_forever, name="PBIBrain desktop server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            self._server.shutdown()
            thread.join(timeout=5)
        self._server.server_close()


def default_static_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return (base / "frontend" / "dist").resolve()


def _show_startup_error(message: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "PBIBrain could not start", 0x10)
        return
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("PBIBrain could not start", message, parent=root)
        root.destroy()
    except Exception:
        print(f"PBIBrain could not start: {message}", file=sys.stderr)


def run() -> int:
    """Launch PBIBrain as a pywebview Windows application."""

    controller: DesktopController | None = None
    server: DesktopServer | None = None
    try:
        configure_native_runtime()
        static_dir = default_static_dir()
        if not (static_dir / "index.html").is_file():
            raise RuntimeError("The PBIBrain interface is missing. Reinstall PBIBrain.")
        import webview  # type: ignore[import-not-found]

        webview.settings["ALLOW_DOWNLOADS"] = True
        controller = DesktopController(static_dir=static_dir)
        server = DesktopServer(controller)
        server.start()
        webview.create_window(
            "PBIBrain",
            server.url,
            js_api=controller,
            width=1440,
            height=900,
            min_size=(1024, 680),
            background_color="#0b1018",
        )
        webview.start(debug=False)
        return 0
    except Exception as exc:
        _show_startup_error(str(exc))
        return 1
    finally:
        if controller is not None:
            controller.shutdown()
        if server is not None:
            server.stop()


__all__ = [
    "DesktopApplication",
    "DesktopController",
    "DesktopServer",
    "default_static_dir",
    "discover_pbip_sources",
    "run",
]
