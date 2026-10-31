#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""api.cgi 行为测试（不需要 NAS / IPMI 硬件 / DSM 环境）。

运行：
    python3 -m unittest discover -s tests -v

覆盖点（含一次真实回归）：
  · 未授权必须返回 unauthorized
  · GET 配置读取
  · POST 且 action **只出现在请求体**时也要正确路由（页面就是这样发的，
    曾经因为只读 QUERY_STRING 而报 "unknown action: (empty)"）
  · 未知 action / 非法参数的错误信息
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CGI = os.path.join(ROOT, "src", "ui", "api.cgi")


class ApiCgiTest(unittest.TestCase):
    def setUp(self):
        self.vardir = tempfile.mkdtemp(prefix="ipmifan-test-")
        self.token = secrets.token_hex(16)
        with open(os.path.join(self.vardir, "token"), "w", encoding="utf-8") as f:
            f.write(self.token + "\n")
        with open(os.path.join(self.vardir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"refresh_seconds": 10, "auto_refresh": True,
                       "temp_warn_c": 50, "temp_crit_c": 70}, f)

    # -- helpers ---------------------------------------------------------
    def call(self, query="", body=b"", method="GET", token=True, ctype="application/x-www-form-urlencoded"):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "SYNOPKG_PKGVAR": self.vardir,
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "CONTENT_TYPE": ctype,
            "CONTENT_LENGTH": str(len(body)),
        }
        if token:
            env["HTTP_X_IPMIFAN_TOKEN"] = self.token
        proc = subprocess.run([sys.executable, CGI], input=body,
                              capture_output=True, env=env, timeout=30)
        raw = proc.stdout.decode("utf-8", "replace")
        head, _, payload = raw.partition("\r\n\r\n")
        self.assertIn("Content-Type: application/json", head)
        return json.loads(payload)

    # -- cases -----------------------------------------------------------
    def test_unauthorized(self):
        data = self.call("action=config", token=False)
        self.assertEqual(data.get("error"), "unauthorized")

    def test_config_read(self):
        data = self.call("action=config")
        self.assertTrue(data["ok"])
        self.assertEqual(data["config"]["refresh_seconds"], 10)

    def test_post_action_in_body_only(self):
        """回归：页面用 POST + 表单提交，action 不在 URL 里。"""
        body = b'action=config_put&payload=%7B%22refresh_seconds%22%3A30%7D'
        data = self.call("", body, method="POST")
        self.assertTrue(data.get("ok"), data)
        self.assertEqual(data["config"]["refresh_seconds"], 30)
        with open(os.path.join(self.vardir, "config.json"), encoding="utf-8") as f:
            stored = json.load(f)
        self.assertEqual(stored["refresh_seconds"], 30)

    def test_config_put_rejects_bad_thresholds(self):
        body = b'action=config_put&payload=%7B%22temp_warn_c%22%3A70%2C%22temp_crit_c%22%3A60%7D'
        data = self.call("", body, method="POST")
        self.assertIn("危险温度", data.get("error", ""))

    def test_unknown_action(self):
        data = self.call("action=nope")
        self.assertIn("unknown action", data.get("error", ""))

    def test_set_mode_rejects_unknown_mode(self):
        body = b'action=set_mode&payload=%7B%22mode%22%3A%22turbo%22%7D'
        data = self.call("", body, method="POST")
        self.assertIn("未知的风扇模式", data.get("error", ""))

    def test_set_duty_range(self):
        body = b'action=set_duty&payload=%7B%22zone%22%3A0%2C%22percent%22%3A150%7D'
        data = self.call("", body, method="POST")
        self.assertIn("0-100", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
