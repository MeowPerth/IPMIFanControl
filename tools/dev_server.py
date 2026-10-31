#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地开发服务器（无需 NAS / 无需 IPMI 硬件）。

做两件事，方便直接改 UI 看效果：
  1. 把 src/ui/ 当静态目录托管（index.html、api.cgi、config、dsm-wrapper.js、images/）
  2. 处理 /api.cgi：默认返回**内置模拟数据**（看着像一台超微主板）；
     加 --real 则把请求真正转给 src/ui/api.cgi 执行（本机有 ipmitool 时读真机）

用法：
    python3 tools/dev_server.py                 # mock，默认 http://127.0.0.1:8799
    python3 tools/dev_server.py --port 9000
    python3 tools/dev_server.py --real          # 执行真实 api.cgi（需要 ipmitool）
"""
import argparse
import json
import mimetypes
import os
import random
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(ROOT, "src", "ui")
VAR_DIR = os.path.join(ROOT, "src", "var")
TOKEN_PLACEHOLDER = "__IPMIFAN_TOKEN__"

MOCK = {
    "fan_mode": "full_speed",
    "duties": [45, 55],
    "fans": [
        {"name": "FAN1", "rpm": 2320},
        {"name": "FAN2", "rpm": 2280},
        {"name": "FAN3", "rpm": 2290},
        {"name": "FAN4", "rpm": 2210},
        {"name": "FANA", "rpm": 1980},
    ],
    "temps": [
        {"name": "CPU Temp", "value": 44},
        {"name": "System Temp", "value": 33},
        {"name": "Peripheral Temp", "value": 47},
        {"name": "PCH Temp", "value": 52},
        {"name": "VRM Temp", "value": 58},
        {"name": "M.2 Temp", "value": 41},
    ],
}
CONFIG = {"refresh_seconds": 10, "auto_refresh": True, "temp_warn_c": 50, "temp_crit_c": 70}


def read_token():
    path = os.path.join(VAR_DIR, "token")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def mock_status():
    jitter = lambda v, n=2: v + random.randint(-n, n)
    return {
        "ok": True,
        "supported": True,
        "fan_mode": MOCK["fan_mode"],
        "duties": list(MOCK["duties"]),
        "fans": [{"name": f["name"], "rpm": jitter(f["rpm"], 40)} for f in MOCK["fans"]],
        "temps": [{"name": t["name"], "value": jitter(t["value"], 1)} for t in MOCK["temps"]],
        "ipmitool": "/var/packages/ipmifancontrol/target/bin/ipmitool",
        "spm_exec": True,
        "duration_ms": random.randint(680, 940),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "IPMIFanDev/1.0"

    def log_message(self, fmt, *args):          # 安静一点
        sys.stderr.write("  %s\n" % (fmt % args))

    # ---- 静态文件 ----
    def _serve_static(self, rel):
        rel = urllib.parse.unquote(rel).lstrip("/")
        path = os.path.normpath(os.path.join(UI_DIR, rel))
        if not path.startswith(UI_DIR) or not os.path.isfile(path):
            self.send_error(404, "not found")
            return
        if path.endswith("index.html"):
            with open(path, "r", encoding="utf-8") as f:
                body = f.read().replace(TOKEN_PLACEHOLDER, read_token())
            body = body.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        else:
            with open(path, "rb") as f:
                body = f.read()
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- api.cgi ----
    def _api(self, method, query, body):
        if self.server.real:
            return self._api_real(method, query, body)

        form = urllib.parse.parse_qs(query, keep_blank_values=True)
        # 页面用 POST 表单提交，action / payload 都在 body 里（URL 不带 query），
        # 与 api.cgi 的解析顺序保持一致：query 优先，其次 body。
        body_form = {}
        if body:
            try:
                body_form = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
            except (UnicodeDecodeError, ValueError):
                body_form = {}
        merged = dict(form)
        for key, value in body_form.items():
            merged.setdefault(key, value)

        action = (merged.get("action") or [""])[0]
        payload = {}
        if "payload" in merged:
            try:
                payload = json.loads(merged["payload"][0])
            except ValueError:
                payload = {}
        elif body:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                payload = {}

        if action == "status":
            return mock_status()
        if action == "config":
            return {"ok": True, "config": CONFIG}
        if action == "config_put":
            for key in CONFIG:
                if key in payload:
                    try:
                        CONFIG[key] = int(payload[key]) if key != "auto_refresh" else bool(payload[key])
                    except (TypeError, ValueError):
                        return {"error": "%s 必须是整数" % key}
            return {"ok": True, "config": CONFIG}
        if action == "set_mode":
            if payload.get("mode") not in ("standard", "full_speed", "optimal", "heavy_io"):
                return {"error": "未知的风扇模式：%s" % payload.get("mode")}
            MOCK["fan_mode"] = payload["mode"]
            return mock_status()
        if action == "set_duty":
            zone = int(payload.get("zone", -1))
            percent = int(payload.get("percent", -1))
            if zone not in (0, 1):
                return {"error": "zone 只能是 0 或 1"}
            if not 0 <= percent <= 100:
                return {"error": "percent 必须在 0-100 之间"}
            MOCK["duties"][zone] = percent
            return mock_status()
        return {"error": "unknown action: %s" % (action or "(empty)")}

    def _api_real(self, method, query, body):
        env = dict(os.environ)
        env.update({
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body or b"")),
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "SYNOPKG_PKGVAR": VAR_DIR,
            "HTTP_X_IPMIFAN_TOKEN": read_token(),
            "PATH": env.get("PATH", "/usr/local/bin:/usr/bin:/bin:/sbin"),
        })
        proc = subprocess.run([sys.executable, os.path.join(UI_DIR, "api.cgi")],
                              input=body or b"", capture_output=True, env=env, timeout=60)
        raw = proc.stdout.decode("utf-8", "replace")
        head, _, payload = raw.partition("\r\n\r\n")
        try:
            return json.loads(payload)
        except ValueError:
            return {"error": "api.cgi 输出异常", "detail": (raw or proc.stderr.decode())[:400]}

    # ---- HTTP 入口 ----
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.rstrip("/") in ("", "/index.html"):
            self._serve_static("index.html")
        elif parsed.path == "/api.cgi":
            self._send_json(self._api("GET", parsed.query, b""))
        else:
            self._serve_static(parsed.path)

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if parsed.path != "/api.cgi":
            self.send_error(404, "not found")
            return
        self._send_json(self._api("POST", parsed.query, body))

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser(description="IPMI Fan Control 本地开发服务器")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--real", action="store_true", help="执行真实 api.cgi（需要 ipmitool）")
    args = ap.parse_args()

    os.makedirs(VAR_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.real = args.real
    print("IPMI Fan Control dev server")
    print("  URL  : http://%s:%d/" % (args.host, args.port))
    print("  模式 : %s" % ("真实 api.cgi" if args.real else "模拟数据"))
    print("  静态 : %s" % UI_DIR)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
