#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IPMI Fan Control CGI（部署为 /webman/3rdparty/ipmifancontrol/api.cgi）

与 IP-Monitor-DSM 的 api.cgi 同一定位：DSM 托管的同源 CGI，被应用窗口内的页面调用。
区别只在于本套件**不需要守护进程**——风扇转速/温度是按需读取的，每次请求一次性
批量调用 ipmitool（转 root 走 spm-exec），把结果整理成 JSON 返回。

协议：GET/POST，action=status|set_mode|set_duty|config|config_put
输出：恒为 HTTP 200 + JSON，成败由 body 的 error 字段表达（规避 CGI Status 头兼容性）。
鉴权：① DSM 会话（官方 authenticate.cgi）② 安装期实例 token（请求头 / Cookie）。
"""
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.parse

AUTH_CGI = "/usr/syno/synoman/webman/modules/authenticate.cgi"
SPM_EXEC_CANDIDATES = ("/usr/local/bin/spm-exec", "/usr/bin/spm-exec")
IPMITOOL_CANDIDATES = ("/usr/bin/ipmitool", "/usr/local/bin/ipmitool")
PKG_NAME = "ipmifancontrol"

MODES = {"standard": 0x00, "full_speed": 0x01, "optimal": 0x02, "heavy_io": 0x04}
MODE_BY_HEX = {v: k for k, v in MODES.items()}

DEFAULT_CONFIG = {
    "refresh_seconds": 10,
    "auto_refresh": True,
    "temp_warn_c": 50,
    "temp_crit_c": 70,
}
CONFIG_LIMITS = {          # 字段 -> (最小, 最大)
    "refresh_seconds": (5, 3600),
    "temp_warn_c": (0, 120),
    "temp_crit_c": (0, 150),
}

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- 输出
def emit(obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    out = sys.stdout.buffer
    out.write(b"Content-Type: application/json; charset=utf-8\r\n")
    out.write(b"Cache-Control: no-store\r\n")
    out.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n")
    out.write(body)


def fail(msg, detail=None):
    obj = {"error": msg}
    if detail:
        obj["detail"] = detail
    emit(obj)


# --------------------------------------------------------------------------- 路径
def var_dir():
    """套件数据目录：/var/packages/ipmifancontrol/var（本地调试时退化为 src/var）。"""
    for candidate in (os.environ.get("IPMIFAN_VAR"),
                      os.environ.get("SYNOPKG_PKGVAR"),
                      "/var/packages/%s/var" % PKG_NAME):
        if candidate and os.path.isdir(candidate):
            return candidate
    return os.path.normpath(os.path.join(HERE, "..", "var"))


def find_ipmitool():
    """优先用套件自带的 bin/ipmitool（与 target/ui/ 同级）。"""
    bundled = os.path.normpath(os.path.join(HERE, "..", "bin", "ipmitool"))
    for path in (bundled,) + IPMITOOL_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def find_spm_exec():
    for path in SPM_EXEC_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


# --------------------------------------------------------------------------- 鉴权
def _cookie_token():
    cookies = os.environ.get("HTTP_COOKIE", "") or ""
    m = re.search(r"(?:^|;\s*)ipmifan_token=([0-9a-fA-F]{16,})", cookies)
    return m.group(1) if m else ""


def token_ok():
    """实例 token 兜底通道（安装期注入页面，请求头或 Cookie 二选一）。"""
    path = os.path.join(var_dir(), "token")
    try:
        with open(path, "r", encoding="utf-8") as f:
            expect = f.read().strip()
    except OSError:
        return False
    if not expect:
        return False
    got = (os.environ.get("HTTP_X_IPMIFAN_TOKEN", "") or "").strip() or _cookie_token()
    return bool(got) and hmac.compare_digest(got, expect)


def session_user():
    """官方机制：CGI 环境里执行 authenticate.cgi；有输出=已登录用户名。"""
    env = dict(os.environ)
    xff = os.environ.get("HTTP_X_FORWARDED_FOR", "")
    if xff:                     # 反代入口下还原真实客户端 IP，否则会话必然对不上
        real = xff.split(",")[0].strip()
        if real:
            env["REMOTE_ADDR"] = real
    if not os.access(AUTH_CGI, os.X_OK):
        return None
    try:
        p = subprocess.run([AUTH_CGI], capture_output=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.decode("utf-8", "replace").strip() or None


def authorized():
    return token_ok() or bool(session_user())


# --------------------------------------------------------------------------- IPMI
READ_ALL = """\
echo '==FAN_MODE=='
__IPMITOOL__ raw 0x30 0x45 0x00 2>&1
echo '==DUTY_0=='
__IPMITOOL__ raw 0x30 0x70 0x66 0x00 0x00 2>&1
echo '==DUTY_1=='
__IPMITOOL__ raw 0x30 0x70 0x66 0x00 0x01 2>&1
echo '==FAN_SDR=='
__IPMITOOL__ sdr type Fan 2>&1
echo '==TEMP_SDR=='
__IPMITOOL__ sdr type Temp 2>&1
"""

SET_ERROR_RE = re.compile(r"error|unable|invalid|failed|denied|unsupported|could not|no such file", re.I)


def _sections(script):
    """执行一段 sh 脚本，按 ==TAG== 标记切块（一次调用完成设置+全部读取）。"""
    ipmitool = find_ipmitool()
    if not ipmitool:
        raise RuntimeError("未找到 ipmitool：套件 bin/ipmitool 缺失或不可执行")
    body = script.replace("__IPMITOOL__", shlex.quote(ipmitool))
    spm = find_spm_exec()
    cmd = [spm, "sh", "-c", body] if spm else ["sh", "-c", body]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ipmitool 执行超时（25s）：BMC 可能无响应")
    except OSError as exc:
        raise RuntimeError("无法启动 ipmitool：%s" % exc)

    text = proc.stdout.decode("utf-8", "replace").replace("\r", "")
    marks = list(re.finditer(r"^==([A-Z0-9_]+)==$", text, flags=re.M))
    out = {}
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[start:end].strip()
    if not out:
        raise RuntimeError("ipmitool 无输出：请在 SimplePermissionManager 中授权本套件以 root 权限运行")
    return out, ipmitool, bool(spm)


def _first_byte(text):
    m = re.search(r"\b([0-9a-fA-F]{2})\b", text or "")
    return int(m.group(1), 16) if m else None


def _parse_sdr(text, unit_pattern):
    """解析 `ipmitool sdr` 的竖线表格：第 1 列是名称，含单位的列是读数。"""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 2 or not cols[0]:
            continue
        reading = ""
        for col in cols[1:]:
            if re.search(unit_pattern, col, flags=re.I):
                reading = col
                break
        if not reading:                       # 无读数（na / 未就绪）
            rows.append((cols[0], None))
            continue
        m = re.search(r"-?\d+(?:\.\d+)?", reading)
        rows.append((cols[0], float(m.group()) if m else None))
    return rows


def read_all(set_cmd=""):
    started = time.time()
    script = ("echo '==SET=='\n" + set_cmd + "\n" if set_cmd else "") + READ_ALL
    sec, ipmitool, spm = _sections(script)

    set_msg = (sec.get("SET") or "").strip()
    if set_msg and SET_ERROR_RE.search(set_msg):
        raise RuntimeError("IPMI 命令执行失败：%s" % set_msg.splitlines()[0])

    mode_byte = _first_byte(sec.get("FAN_MODE", ""))
    duties = [_first_byte(sec.get("DUTY_0", "")), _first_byte(sec.get("DUTY_1", ""))]

    fans = [{"name": name,
             "rpm": int(rpm) if rpm is not None else None}
            for name, rpm in _parse_sdr(sec.get("FAN_SDR", ""), r"\bRPM\b")]
    temps = [{"name": name, "value": round(val, 1)}
             for name, val in _parse_sdr(sec.get("TEMP_SDR", ""), r"degrees?\s*C|°C")
             if val is not None]

    return {
        "ok": True,
        "supported": mode_byte in MODE_BY_HEX or bool(fans),
        "fan_mode": MODE_BY_HEX.get(mode_byte),
        "duties": duties,
        "fans": fans,
        "temps": temps,
        "ipmitool": ipmitool,
        "spm_exec": spm,
        "duration_ms": int((time.time() - started) * 1000),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# --------------------------------------------------------------------------- 配置
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(os.path.join(var_dir(), "config.json"), "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            cfg.update({k: stored[k] for k in DEFAULT_CONFIG if k in stored})
    except (OSError, ValueError):
        pass
    return cfg


def sanitize_config(payload):
    """白名单 + 范围收敛；危险温度必须高于告警温度。"""
    cfg = load_config()
    for key, (lo, hi) in CONFIG_LIMITS.items():
        if key in payload:
            try:
                cfg[key] = max(lo, min(hi, int(float(payload[key]))))
            except (TypeError, ValueError):
                raise ValueError("%s 必须是整数" % key)
    if "auto_refresh" in payload:
        cfg["auto_refresh"] = bool(payload["auto_refresh"])
    if cfg["temp_crit_c"] <= cfg["temp_warn_c"]:
        raise ValueError("危险温度必须高于告警温度")
    return cfg


def save_config(cfg):
    path = os.path.join(var_dir(), "config.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return cfg


# --------------------------------------------------------------------------- 主流程
def read_body():
    try:
        length = int(os.environ.get("CONTENT_LENGTH", "0") or 0)
    except ValueError:
        length = 0
    return sys.stdin.buffer.read(length) if length else b""


def parse_payload(raw, form):
    """兼容 JSON body 与表单 payload=<json> 两种提交方式。"""
    ctype = (os.environ.get("CONTENT_TYPE", "") or "").lower()
    if raw:
        if "json" in ctype:
            try:
                return json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                raise ValueError("请求体不是合法 JSON")
        parsed = urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
        if "payload" in parsed:
            try:
                return json.loads(parsed["payload"][0])
            except ValueError:
                raise ValueError("payload 不是合法 JSON")
        return {k: v[0] for k, v in parsed.items()}
    if "payload" in form:
        try:
            return json.loads(form["payload"][0])
        except ValueError:
            raise ValueError("payload 不是合法 JSON")
    return {k: v[0] for k, v in form.items()}


def main():
    method = os.environ.get("REQUEST_METHOD", "GET").upper()
    form = urllib.parse.parse_qs(os.environ.get("QUERY_STRING", ""), keep_blank_values=True)
    action = (form.get("action") or [""])[0]

    if action not in ("status", "set_mode", "set_duty", "config", "config_put"):
        fail("unknown action: %s" % (action or "(empty)"))
        return

    if not authorized():
        fail("unauthorized")
        return

    try:
        if action == "status":
            emit(read_all())

        elif action == "config":
            emit({"ok": True, "config": load_config()})

        elif action in ("set_mode", "set_duty", "config_put"):
            if method != "POST":
                return fail("method not allowed")
            payload = parse_payload(read_body(), form)
            if not isinstance(payload, dict):
                return fail("payload 必须是对象")

            if action == "config_put":
                emit({"ok": True, "config": save_config(sanitize_config(payload))})
                return

            if action == "set_mode":
                mode = payload.get("mode")
                if mode not in MODES:
                    return fail("未知的风扇模式：%s" % mode)
                emit(read_all("__IPMITOOL__ raw 0x30 0x45 0x01 0x%02x 2>&1" % MODES[mode]))
                return

            try:
                zone = int(payload.get("zone", 0))
                percent = int(payload.get("percent", 0))
            except (TypeError, ValueError):
                return fail("zone / percent 必须是整数")
            if zone not in (0, 1):
                return fail("zone 只能是 0 或 1")
            if not 0 <= percent <= 100:
                return fail("percent 必须在 0-100 之间")
            emit(read_all("__IPMITOOL__ raw 0x30 0x70 0x66 0x01 0x%02x 0x%02x 2>&1"
                          % (zone, percent)))

    except (ValueError, RuntimeError) as exc:
        fail(str(exc))
    except Exception as exc:                  # 兜底：绝不把 500/堆栈抛给页面
        fail("内部错误：%s" % exc)


if __name__ == "__main__":
    main()
