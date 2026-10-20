from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if sys.version_info < (3, 10):
    sys.exit("python 3.10 or newer is required")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

DEFAULT_WORKSPACE = (Path.home() / "agent-workspace").resolve()
os.environ.setdefault("WORKSPACE_DIR", str(DEFAULT_WORKSPACE))

import tools

HOST = "127.0.0.1"
PORT = int(os.getenv("PORT", "3456"))

ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
MAX_BODY_BYTES = 10 * 1024 * 1024

CONFIG_DIR = Path.home() / ".deepseek-web-agent"

def load_or_create_token() -> str:
    env_token = os.getenv("BRIDGE_TOKEN", "").strip()
    if env_token:
        return env_token

    token_file = CONFIG_DIR / "token"
    try:
        if token_file.is_file():
            saved = token_file.read_text(encoding="utf-8").strip()
            if len(saved) >= 32:
                return saved
    except OSError:
        pass

    new_token = secrets.token_urlsafe(32)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        token_file.write_text(new_token, encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass
    except OSError as exc:
        print(f"warn: could not save the token ({exc}); it will change on every restart.")
    return new_token

TOKEN = load_or_create_token()

def workspace_is_too_broad(p: Path) -> bool:
    return p == p.parent or p == Path.home().resolve()

def apply_workspace(p: Path) -> tuple[bool, str]:
    p = p.resolve()
    if workspace_is_too_broad(p):
        return False, "refusing to use a drive root or your home directory as the workspace."
    p.mkdir(parents=True, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = str(p)
    print(f"\n[WORKSPACE CHANGED] {p}")
    return True, str(p)

def choose_folder_dialog(initial_dir: str) -> str | None:
    try:
        tk_script = (
            "import tkinter as tk, sys\n"
            "from tkinter import filedialog\n"
            "root = tk.Tk()\n"
            "root.overrideredirect(True)\n"
            "root.geometry('0x0+0+0')\n"
            "root.deiconify()\n"
            "root.lift()\n"
            "root.attributes('-topmost', True)\n"
            "root.focus_force()\n"
            "init_dir = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "folder = filedialog.askdirectory(parent=root, initialdir=init_dir, title='Select Workspace Folder')\n"
            "root.destroy()\n"
            "if folder:\n"
            "    print(folder)\n"
        )
        res = subprocess.run([sys.executable, "-c", tk_script, initial_dir], capture_output=True, text=True, timeout=300)
        out = res.stdout.strip()
        if out and Path(out).is_dir():
            return out
    except Exception:
        pass

    if sys.platform != "win32":
        return None

    try:
        escaped_dir = initial_dir.replace("'", "''")
        ps_cmd = (
            f"[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
            f"$form = New-Object System.Windows.Forms.Form; "
            f"$form.TopMost = $true; "
            f"$form.Opacity = 0; "
            f"$form.ShowInTaskbar = $false; "
            f"$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None; "
            f"$form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized; "
            f"$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$f.SelectedPath = '{escaped_dir}'; "
            f"$f.Description = 'Select Workspace Folder'; "
            f"if ($f.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {{ Write-Host -NoNewline $f.SelectedPath }}; "
            f"$form.Dispose()"
        )
        res = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", ps_cmd], capture_output=True, text=True, timeout=300)
        out = res.stdout.strip()
        if out and Path(out).is_dir():
            return out
    except Exception:
        pass
    return None

class AgentBridgeHandler(BaseHTTPRequestHandler):

    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _request_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in ALLOWED_HOSTS:
            self._send_json(403, {"ok": False, "error": "forbidden host"})
            return False

        auth = self.headers.get("Authorization") or ""
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), TOKEN.encode("utf-8")):
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_OPTIONS(self) -> None:
        self._send_json(405, {"ok": False, "error": "method not allowed"})

    def do_GET(self) -> None:
        if not self._request_allowed():
            return

        url_path = self.path.split("?")[0].rstrip("/")
        if url_path in ("", "/api/status", "/status", "/health"):
            ws = tools.get_workspace_dir()
            self._send_json(200, {
                "ok": True,
                "status": "online",
                "workspace": str(ws),
                "workspace_name": ws.name,
                "tools": tools.TOOL_NAMES,
            })
        elif url_path == "/api/workspace":
            ws = tools.get_workspace_dir()
            tree = tools.list_dir_tree(ws, max_depth=2)
            self._send_json(200, {
                "ok": True,
                "workspace": str(ws),
                "workspace_name": ws.name,
                "files": tree,
            })
        else:
            self._send_json(404, {"ok": False, "error": f"Endpoint '{url_path}' not found"})

    def do_POST(self) -> None:
        if not self._request_allowed():
            return

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._send_json(415, {"ok": False, "error": "Content-Type must be application/json"})
            return

        url_path = self.path.split("?")[0].rstrip("/")
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "Invalid Content-Length"})
            return
        if content_length < 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413, {"ok": False, "error": "Request body too large"})
            return
        raw_body = self.rfile.read(content_length)

        try:
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(body, dict):
                raise ValueError("JSON body must be an object")
        except Exception as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON payload: {e}"})
            return

        if url_path in ("/api/execute", "/execute"):
            tool_name = body.get("name") or body.get("tool")
            tool_args = body.get("arguments") or body.get("args") or {}

            if not tool_name or not isinstance(tool_name, str):
                self._send_json(400, {"ok": False, "error": "Missing 'name' or 'tool' field"})
                return
            if not isinstance(tool_args, dict):
                self._send_json(400, {"ok": False, "error": "'arguments' must be an object"})
                return

            args_preview = json.dumps(tool_args, ensure_ascii=False)
            if len(args_preview) > 300:
                args_preview = args_preview[:300] + "..."
            print(f"\n[TOOL CALL] {tool_name}")
            print(f"   Args: {args_preview}")

            result = tools.execute_tool(tool_name, tool_args)
            status = result.get("status", "ok")
            exit_code = result.get("exit_code")
            output = result.get("output", "")

            status_symbol = "[OK]" if status == "ok" else "[ERR]"
            print(f"   {status_symbol} status={status}" + (f", exit_code={exit_code}" if exit_code is not None else ""))
            out_preview = output.strip().replace("\n", " ")[:120]
            print(f"   Output: {out_preview}..." if len(output) > 120 else f"   Output: {out_preview}")

            self._send_json(200, {
                "ok": True,
                "tool": tool_name,
                "status": status,
                "exit_code": exit_code,
                "output": output,
            })

        elif url_path in ("/api/choose_folder", "/choose_folder"):
            current_ws = tools.get_workspace_dir()
            selected = choose_folder_dialog(str(current_ws))
            if selected:
                ok, info = apply_workspace(Path(selected))
                if not ok:
                    self._send_json(200, {
                        "ok": True,
                        "workspace": str(current_ws),
                        "workspace_name": current_ws.name,
                        "changed": False,
                        "error": info,
                    })
                    return
                p = Path(info)
                self._send_json(200, {
                    "ok": True,
                    "workspace": str(p),
                    "workspace_name": p.name,
                    "changed": True,
                })
            else:
                self._send_json(200, {
                    "ok": True,
                    "workspace": str(current_ws),
                    "workspace_name": current_ws.name,
                    "changed": False,
                })

        elif url_path in ("/api/workspace", "/workspace"):
            new_path = body.get("path")
            if not new_path or not isinstance(new_path, str):
                self._send_json(400, {"ok": False, "error": "Missing 'path' field"})
                return

            try:
                ok, info = apply_workspace(Path(new_path))
            except Exception as e:
                self._send_json(500, {"ok": False, "error": f"Failed to set workspace: {e}"})
                return
            if not ok:
                self._send_json(400, {"ok": False, "error": info})
                return
            p = Path(info)
            self._send_json(200, {
                "ok": True,
                "workspace": str(p),
                "workspace_name": p.name,
                "changed": True,
            })
        else:
            self._send_json(404, {"ok": False, "error": f"Endpoint '{url_path}' not found"})

    def log_message(self, format: str, *args: Any) -> None:
        pass

def run_server() -> None:
    ws = tools.get_workspace_dir()
    server = ThreadingHTTPServer((HOST, PORT), AgentBridgeHandler)
    print(f"deepseek web agent bridge running on http://{HOST}:{PORT}")
    print(f"workspace: {ws}")
    print()
    print("bridge token (paste it into the userscript when it asks):")
    print(f"    {TOKEN}")
    print()
    print("NOTE: run_command executes with YOUR user's permissions and is NOT sandboxed.")
    print("only the file tools are restricted to the workspace folder.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()

if __name__ == "__main__":
    run_server()
