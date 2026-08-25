#!/bin/sh
# IPMI Fan Control API - Minimal proxy
# Uses ONE spm-exec call per request instead of multiple.

IPMITOOL=""
for p in /usr/bin/ipmitool /usr/local/bin/ipmitool; do
    [ -x "$p" ] && { IPMITOOL="$p"; break; }
done
[ -z "$IPMITOOL" ] && IPMITOOL="ipmitool"

SPM_EXEC=""
[ -x /usr/local/bin/spm-exec ] && SPM_EXEC="/usr/local/bin/spm-exec"

QUERY_STRING="${QUERY_STRING:-}"
REQUEST_METHOD="${REQUEST_METHOD:-GET}"
ACTION=""
for param in $(echo "$QUERY_STRING" | tr '&' ' '); do
    case "$param" in action=*) ACTION="${param#action=}" ;; esac
done

HDR='Content-Type: text/plain; charset=utf-8\r\nCache-Control: no-cache\r\n\r\n'

# All-in-one ipmitool commands, executed in a single spm-exec call
IPMI_ALL='
echo ===FAN_MODE===
"IPMITOOL" raw 0x30 0x45 0x00
echo ===DUTY_0===
"IPMITOOL" raw 0x30 0x70 0x66 0x00 0x00
echo ===DUTY_1===
"IPMITOOL" raw 0x30 0x70 0x66 0x00 0x01
echo ===FAN_SDR===
"IPMITOOL" sdr type Fan
echo ===TEMP_SDR===
"IPMITOOL" sdr type Temp
'

case "$ACTION" in
    fan_mode)
        printf "$HDR"
        if [ "$REQUEST_METHOD" = "POST" ]; then
            body=""; CL="${CONTENT_LENGTH:-0}"
            [ "${CL:-0}" -gt 0 ] 2>/dev/null && body=$(dd bs=1 count="$CL" 2>/dev/null)
            mode=$(echo "$body"|sed -n 's/.*"mode"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
            case "$mode" in
                standard)  hex="0x00" ;; full_speed) hex="0x01" ;;
                optimal)   hex="0x02" ;; heavy_io)  hex="0x04" ;;
                *) echo "err"; exit 0 ;;
            esac
            # Set mode, then read all data back — 1 spm-exec
            ALL=$(echo "$IPMI_ALL" | sed "s|\"IPMITOOL\"|${IPMITOOL}|g")
            SET_CMD="${IPMITOOL} raw 0x30 0x45 0x01 ${hex}"
            if [ -n "$SPM_EXEC" ]; then
                "$SPM_EXEC" sh -c "${SET_CMD} 2>/dev/null && ${ALL}" 2>/dev/null
            else
                ${SET_CMD} 2>/dev/null
                echo "$ALL" | sh 2>/dev/null
            fi
        else
            ALL=$(echo "$IPMI_ALL" | sed "s|\"IPMITOOL\"|${IPMITOOL}|g")
            if [ -n "$SPM_EXEC" ]; then
                "$SPM_EXEC" sh -c "$ALL" 2>/dev/null
            else
                echo "$ALL" | sh 2>/dev/null
            fi
        fi
        ;;
    duty)
        printf "$HDR"
        zone="${QUERY_STRING#*zone=}"
        zone="${zone%%&*}"
        zone="${zone:-0}"
        hex_zone=$(printf '0x%02x' "$zone")
        ALL=$(echo "$IPMI_ALL" | sed "s|\"IPMITOOL\"|${IPMITOOL}|g")
        if [ "$REQUEST_METHOD" = "POST" ]; then
            body=""; CL="${CONTENT_LENGTH:-0}"
            [ "${CL:-0}" -gt 0 ] 2>/dev/null && body=$(dd bs=1 count="$CL" 2>/dev/null)
            pct=$(echo "$body"|sed -n 's/.*"percent"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p')
            hex_pct=$(printf '0x%02x' "${pct:-0}")
            SET_CMD="${IPMITOOL} raw 0x30 0x70 0x66 0x01 ${hex_zone} ${hex_pct}"
            if [ -n "$SPM_EXEC" ]; then
                "$SPM_EXEC" sh -c "${SET_CMD} 2>/dev/null && ${ALL}" 2>/dev/null
            else
                ${SET_CMD} 2>/dev/null
                echo "$ALL" | sh 2>/dev/null
            fi
        else
            if [ -n "$SPM_EXEC" ]; then
                "$SPM_EXEC" sh -c "$ALL" 2>/dev/null
            else
                echo "$ALL" | sh 2>/dev/null
            fi
        fi
        ;;
    all)
        printf "$HDR"
        ALL=$(echo "$IPMI_ALL" | sed "s|\"IPMITOOL\"|${IPMITOOL}|g")
        if [ -n "$SPM_EXEC" ]; then
            "$SPM_EXEC" sh -c "$ALL" 2>/dev/null
        else
            echo "$ALL" | sh 2>/dev/null
        fi
        ;;
    *)
        printf 'Content-Type: text/plain\r\n\r\n?'
        ;;
esac
