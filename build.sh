#!/usr/bin/env bash
# IPMI Fan Control SPK 一键打包：产物 dist/ipmifancontrol_x86_64-dsm7_<ver>-<build>.spk
# .spk = 未压缩 tar{ INFO, package.tgz, scripts/, conf/, PACKAGE_ICON*.PNG, LICENSE }
# 只需 bash / tar / gzip / md5sum / python3，无需 Synology SDK 或 spksrc。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PKG_NAME="ipmifancontrol"
VERSION="1.0.0"
BUILD="0002"
# 内置 ipmitool 为 x86-64 ELF（动态链接 libc），因此只声明 x86 平台
ARCH="apollolake avoton braswell broadwell broadwellnk broadwellnkv2 broadwellntbap bromolow cedarview denverton epyc7002 geminilake geminilakenk grantley kvmx64 purley x86_64"
SPK_ARCH="x86_64"
SPK_FILE="${ROOT}/dist/${PKG_NAME}_${SPK_ARCH}-dsm7_${VERSION}-${BUILD}.spk"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
STAGE="$WORK/stage"
mkdir -p "$STAGE/bin" "$STAGE/ui/images" "$STAGE/var" \
         "$WORK/scripts" "$WORK/conf" "$ROOT/dist"

echo "==> 自检：Python CGI 语法 / JSON 文件"
python3 - <<'PY'
import json
src = open("src/ui/api.cgi", encoding="utf-8").read()
compile(src, "src/ui/api.cgi", "exec")
for path in ("src/ui/config", "spk/var-default-config.json", "spk/conf/privilege"):
    json.load(open(path, encoding="utf-8"))
print("   api.cgi / JSON OK")
PY
grep -q "__IPMIFAN_TOKEN__" src/ui/index.html \
  || { echo "ERROR: src/ui/index.html 缺少 __IPMIFAN_TOKEN__ 占位符（installer 无法注入 token）"; exit 1; }
for icon in 16 24 32 48 64 72 256; do
  [ -f "src/ui/images/ipmifan_${icon}.png" ] || { echo "ERROR: 缺少图标 src/ui/images/ipmifan_${icon}.png"; exit 1; }
done

echo "==> 组装 package.tgz 内容"
install -m 755 "$ROOT/src/bin/ipmitool"        "$STAGE/bin/ipmitool"
install -m 755 "$ROOT/src/ui/api.cgi"          "$STAGE/ui/api.cgi"
install -m 644 "$ROOT/src/ui/index.html"       "$STAGE/ui/index.html"
install -m 644 "$ROOT/src/ui/config"           "$STAGE/ui/config"
install -m 644 "$ROOT/src/ui/dsm-wrapper.js"   "$STAGE/ui/dsm-wrapper.js"
install -m 644 "$ROOT/src/ui/images/"ipmifan_*.png "$STAGE/ui/images/"
install -m 644 "$ROOT/spk/var-default-config.json" "$STAGE/var/config.json"

echo "==> scripts / conf / 图标 / LICENSE"
for f in installer preinst postinst preuninst postuninst preupgrade postupgrade; do
  [ -f "$ROOT/spk/scripts/$f" ] || { echo "缺少 spk/scripts/$f"; exit 1; }
  install -m 755 "$ROOT/spk/scripts/$f" "$WORK/scripts/$f"
done
install -m 644 "$ROOT/spk/conf/privilege" "$WORK/conf/privilege"
install -m 644 "$ROOT/src/ui/images/ipmifan_64.png"  "$WORK/PACKAGE_ICON.PNG"     # DSM7 64x64
install -m 644 "$ROOT/src/ui/images/ipmifan_256.png" "$WORK/PACKAGE_ICON_256.PNG"
install -m 644 "$ROOT/LICENSE" "$WORK/LICENSE"

echo "==> 生成 package.tgz（gzip，固定成员顺序）"
( cd "$STAGE" && tar czf "$WORK/package.tgz" bin ui var )

CHECKSUM="$(md5sum "$WORK/package.tgz" | cut -d' ' -f1)"
echo "==> package.tgz md5 = $CHECKSUM"

# INFO 只允许 key="value" 行，不能有任何注释/空行——DSM 的 spk 解析器会因此拒绝安装
# （dsmappname 必须等于 dsm-wrapper.js 中 Ext.define 的 AppInstance 类名）
cat > "$WORK/INFO" <<EOF
package="$PKG_NAME"
version="$VERSION-$BUILD"
description="Monitor fan speed and temperatures via IPMI and switch Supermicro fan modes."
description_chs="通过 IPMI 监测风扇转速与温度，并切换超微主板的四种风扇模式。"
description_cht="透過 IPMI 監測風扇轉速與溫度，並切換超微主機板的四種風扇模式。"
arch="$ARCH"
os_min_ver="7.3-81180"
displayname="IPMI Fan Control"
dsmuidir="ui"
dsmappname="MeowPerth.IPMIFanControl.AppInstance"
maintainer="小H酱"
maintainer_url="https://github.com/MeowPerth/IPMIFanControl"
distributor="小H酱"
distributor_url="https://github.com/MeowPerth/IPMIFanControl"
helpurl="https://github.com/MeowPerth/IPMIFanControl#readme"
support_url="https://github.com/MeowPerth/IPMIFanControl/issues"
reloadui="yes"
changelog="$VERSION-$BUILD: 套件风格对齐 IP-Monitor-DSM（src/spk 结构、原生窗口、明暗主题 UI、JSON API）"
checksum="$CHECKSUM"
EOF
# 自检：INFO 必须全部是 key="value" 行
if grep -Evq '^[A-Za-z_]+=".*"$' "$WORK/INFO"; then
  echo "ERROR: INFO 含非法行："; grep -Env '^[A-Za-z_]+=".*"$' "$WORK/INFO"; exit 1
fi

echo "==> 打包 .spk（未压缩 tar）"
rm -f "$SPK_FILE"
( cd "$WORK" && tar cpf "$SPK_FILE" INFO package.tgz scripts conf \
    PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG LICENSE )

echo "==> 产物：$SPK_FILE ($(du -h "$SPK_FILE" | cut -f1))"
tar tf "$SPK_FILE"
echo "==> package.tgz 内容："
tar xfO "$SPK_FILE" package.tgz | tar tzf -
