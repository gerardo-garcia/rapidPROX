#!/usr/bin/env python3

import os
import signal
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.getcwd()
print(f"Control server base dir: {BASE_DIR}", flush=True)

def reap_children(signum, frame):
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            print(f"Reaped child process pid={pid}", flush=True)
        except ChildProcessError:
            break


def prox_status():
    result = subprocess.run(
        "ps -ef | grep '[p]rox' || true",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.stdout.strip():
        return f"PROX running:\n{result.stdout}"
    return "PROX not running\n"

def resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)

def make_control_handler():
    class ControlHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                self.reply(200, prox_status())

            if self.path.startswith("/file"):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)

                path = query.get("path", [""])[0]
                
                if not path:
                    self.reply(400, "missing path\n")
                    return

                path = resolve_path(path)

                if not os.path.exists(path):
                    self.reply(404, "file not found: {}\n".format(path))
                    return

                with open(path, "rb") as f:
                    data = f.read()

                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            self.reply(404, "not found\n")

        def do_PUT(self):
            if not self.path.startswith("/file"):
                self.reply(404, "not found\n")
                return

            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            path = query.get("path", [""])[0]
            if not path:
                self.reply(400, "missing path\n")
                return

            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)

            with open(path, "wb") as f:
                f.write(data)

            self.reply(200, f"file written: {path}\n")

        def do_POST(self):
            if self.path != "/cmd":
                self.reply(404, "not found\n")
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")

            params = urllib.parse.parse_qs(body)
            command = params.get("command", [""])[0]

            if not command:
                self.reply(400, "missing command\n")
                return

            result = subprocess.run(
                command,
                shell=True,
                cwd="/opt/rapid",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            output = result.stdout
            if result.returncode != 0:
                output += f"\n[exit_code={result.returncode}]\n"

            self.reply(200, output)

        def reply(self, code, text):
            body = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ControlHandler


def start_control_server():
    print("Starting control server on port 9090", flush=True)
    handler = make_control_handler()
    ThreadingHTTPServer(("0.0.0.0", 9090), handler).serve_forever()


def main():
    signal.signal(signal.SIGCHLD, reap_children)
    try:
        open("/opt/rapid/system_ready_for_rapid", "a").close()
    except Exception as e:
        print(f"Error creating readiness file: {e}", flush=True)

    start_control_server()


if __name__ == "__main__":
    main()
