#!/bin/bash
# SPK Build Script for IPMI Fan Control
# Usage: ./build_spk.sh

set -e

PACKAGE_NAME="IPMIFanControl"
VERSION="1.0-0001"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/tmp/_spk_build_$$"
SPK_FILE="${SCRIPT_DIR}/${PACKAGE_NAME}-${VERSION}.spk"

echo "=== Building ${PACKAGE_NAME} SPK v${VERSION} ==="

# Clean
rm -rf "${BUILD_DIR}" "${SPK_FILE}"
mkdir -p "${BUILD_DIR}"

# ---- INFO + LICENSE + conf ----
cp "${SCRIPT_DIR}/INFO" "${BUILD_DIR}/"
cp "${SCRIPT_DIR}/LICENSE" "${BUILD_DIR}/"
cp -r "${SCRIPT_DIR}/conf" "${BUILD_DIR}/"

# ---- Create package.tgz ----
PKG_TGZ_DIR="/tmp/_package_tgz_$$"
rm -rf "${PKG_TGZ_DIR}"
mkdir -p "${PKG_TGZ_DIR}/ui" "${PKG_TGZ_DIR}/bin"

# UI files (index.html, api.cgi, config, Main.js, images/)
cp "${SCRIPT_DIR}/ui/index.html" "${PKG_TGZ_DIR}/ui/"
cp "${SCRIPT_DIR}/ui/api.cgi" "${PKG_TGZ_DIR}/ui/"
cp "${SCRIPT_DIR}/ui/config" "${PKG_TGZ_DIR}/ui/"
cp "${SCRIPT_DIR}/ui/Main.js" "${PKG_TGZ_DIR}/ui/"
chmod 755 "${PKG_TGZ_DIR}/ui/api.cgi"
if [ -d "${SCRIPT_DIR}/ui/images" ]; then
    cp -r "${SCRIPT_DIR}/ui/images" "${PKG_TGZ_DIR}/ui/"
fi

# Bundled ipmitool
if [ -d "${SCRIPT_DIR}/bin" ]; then
    cp "${SCRIPT_DIR}/bin/"* "${PKG_TGZ_DIR}/bin/"
    chmod 755 "${PKG_TGZ_DIR}/bin/"*
fi

# Lifecycle scripts (go into package.tgz and also SPK root)
mkdir -p "${PKG_TGZ_DIR}/scripts"
for script in start-stop-status preinst postinst preuninst postuninst preupgrade postupgrade; do
    [ -f "${SCRIPT_DIR}/scripts/${script}" ] && cp "${SCRIPT_DIR}/scripts/${script}" "${PKG_TGZ_DIR}/scripts/"
done

cd "${PKG_TGZ_DIR}"
tar cf - . | xz -1 > "${BUILD_DIR}/package.tgz"
cd "${SCRIPT_DIR}"
rm -rf "${PKG_TGZ_DIR}"

# ---- Icons ----
cp "${SCRIPT_DIR}/PACKAGE_ICON.PNG" "${BUILD_DIR}/"
cp "${SCRIPT_DIR}/PACKAGE_ICON_256.PNG" "${BUILD_DIR}/"

# ---- Scripts (must be at SPK root for DSM to find) ----
mkdir -p "${BUILD_DIR}/scripts"
for script in start-stop-status preinst postinst preuninst postuninst preupgrade postupgrade; do
    [ -f "${SCRIPT_DIR}/scripts/${script}" ] && cp "${SCRIPT_DIR}/scripts/${script}" "${BUILD_DIR}/scripts/"
done
chmod 755 "${BUILD_DIR}/scripts/"*

# ---- Create SPK ----
chmod 644 "${BUILD_DIR}/INFO" "${BUILD_DIR}/LICENSE" "${BUILD_DIR}/PACKAGE_ICON.PNG" "${BUILD_DIR}/PACKAGE_ICON_256.PNG"
cd "${BUILD_DIR}"
tar -cf "${SPK_FILE}" *
cd "${SCRIPT_DIR}"
rm -rf "${BUILD_DIR}"

echo "=== Build Complete ==="
echo "SPK: ${SPK_FILE} ($(du -h "${SPK_FILE}" | cut -f1))"
echo ""
echo "package.tgz contents:"
tar -xf "${SPK_FILE}" package.tgz -O | xz -d | tar -t
