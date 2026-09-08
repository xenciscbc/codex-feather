"""Capture a native Codex tool-registration request without calling a real model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import subprocess
import threading


def registered_tools(request: dict) -> list[dict]:
    return request.get("tools", []) + [tool for item in request.get("input", [])
                                       if item.get("type") == "additional_tools" for tool in item["tools"]]


def render_messages(messages: list[dict]) -> str:
    return "\n".join(block.get("text", "") for message in messages for block in message.get("content", []))


def skill_paths(rendered: str, directory_name: str) -> list[Path]:
    roots = dict(re.findall(r"- `(r\d+)` = `([^`]+)`", rendered))
    aliases = re.findall(r"\(file: (r\d+)/" + re.escape(directory_name) + r"/SKILL\.md\)", rendered)
    return [(Path(roots[alias]) / directory_name / "SKILL.md").resolve() for alias in aliases]


def capture_tools(codex: str, project: Path, user_home: Path, codex_home: Path) -> dict:
    requests = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(json.loads(self.rfile.read(length)))
            body = b'{"error":{"message":"Feather discovery capture complete","type":"probe_complete"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith(("CODEX_", "OPENAI_"))}
    environment.update(CODEX_HOME=str(codex_home), HOME=str(user_home), USERPROFILE=str(user_home))
    if os.name == "nt":
        environment.update(HOMEDRIVE=user_home.drive, HOMEPATH=str(user_home)[len(user_home.drive):])
    provider = ('model_providers.feather_probe={name="Feather local probe",'
                f'base_url="http://127.0.0.1:{server.server_port}/v1",'
                'wire_api="responses",requires_openai_auth=false,request_max_retries=0,stream_max_retries=0}')
    command = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--json",
               "--model", "gpt-5.6-sol", "-c", 'model_provider="feather_probe"', "-c", provider,
               "-c", "agents.enabled=true", "Do not perform work. This is a local tool-discovery capture."]
    try:
        result = subprocess.run(command, cwd=project, env=environment, capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if not requests:
        raise AssertionError("No native registration request captured: " + result.stderr[-2000:])
    return requests[0]
