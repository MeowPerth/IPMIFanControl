# IPMIFanControl（IPMI 风扇控制）

适用于 **群晖（Synology）DSM** 的第三方套件（SPK），通过 IPMI 查询服务器风扇转速与系统温度，并支持切换多种风扇模式。

- **维护者**：小H酱
- **版本**：1.0-0001
- **最低 DSM 版本**：7.3-81180
- **适用架构**：x86 / x86_64 及常见群晖平台（apollolake、broadwell、purley、denverton、epyc7002 等）

## 功能特性

- 🌀 **风扇监控**：实时查询所有风扇的转速（RPM）
- 🌡️ **温度监控**：实时查询系统各温度传感器读数（≥50°C 变黄、≥70°C 变红）
- ⚙️ **四种风扇模式**（Supermicro IPMI 私有命令）：

  | 模式 | IPMI 值 | 说明 |
  |------|---------|------|
  | Standard（标准） | `0x00` | 默认自动调速 |
  | Full Speed（全速） | `0x01` | 风扇全速运转，可自定义转速 |
  | Optimal（静音） | `0x02` | 优先静音 |
  | Heavy I/O（重IO） | `0x04` | 高负载场景 |

- 🔧 **自定义转速**：在 Full Speed 模式下，可分别设置 Zone 0（CPU/系统）与 Zone 1（机箱/存储）的风扇转速百分比（0–100%）

## 运行要求

1. 群晖 DSM **7.3** 及以上
2. 主板 IPMI 支持（主要针对 **Supermicro（超微）** 主板）
3. 已安装 [SimplePermissionManager](https://synopackage.com/simplepermissionmanager/) 套件，并授权本套件以 **root** 权限运行（用于调用 `spm-exec` 执行 `ipmitool`）
4. `ipmitool` 命令（本套件 `bin/` 目录已内置，安装时自动部署）

## 安装方法

1. 安装 **SimplePermissionManager** 套件
2. 安装本套件（`IPMIFanControl-1.0-0001.spk`）
3. 在 SimplePermissionManager 中授权本套件以 root 权限启动
4. 在套件中心启用本套件，打开应用窗口即可使用

> 本套件通过 CGI（`api.cgi`）按需调用 IPMI 命令，无后台常驻服务，安装/卸载不影响其他套件。

## 使用界面

- 顶部：连接状态、手动刷新按钮、最后刷新时间
- **风扇模式**：四个模式按钮一键切换；选中 Full Speed 时展开自定义转速面板
- **风扇详情**：各风扇名称与实时转速
- **温度**：各温度传感器名称与实时温度

## 构建 SPK

```bash
./build_spk.sh
```

脚本会在当前目录生成 `IPMIFanControl-1.0-0001.spk`，并在末尾打印 `package.tgz` 内容清单。

## 目录结构

```
IPMIFanControl/
├── INFO                     # 套件元信息（名称/版本/架构/最低 DSM 版本等）
├── LICENSE                  # 声明与功能说明
├── build_spk.sh             # SPK 打包脚本
├── PACKAGE_ICON.PNG         # 套件图标（小）
├── PACKAGE_ICON_256.PNG     # 套件图标（大）
├── bin/
│   └── ipmitool             # 内置 ipmitool 二进制
├── conf/
│   └── privilege            # 权限配置（默认以 package 身份运行）
├── scripts/                 # DSM 生命周期脚本
│   ├── preinst / postinst
│   ├── preuninst / postuninst
│   ├── preupgrade / postupgrade
│   └── start-stop-status
└── ui/
    ├── index.html           # 前端页面（深色主题，单文件）
    ├── api.cgi              # CGI 后端，代理 ipmitool 命令
    ├── Main.js              # DSM 应用窗口（iframe 加载 index.html）
    ├── config               # DSM 应用配置
    └── images/              # 应用图标
```

## API 说明（`ui/api.cgi`）

所有请求通过单次 `spm-exec` 调用批量执行 ipmitool 命令，降低开销。

| Action | 方法 | 说明 |
|--------|------|------|
| `all` | GET | 一次性获取风扇模式、两区转速、风扇列表、温度列表 |
| `fan_mode` | GET / POST | 读取 / 设置风扇模式（POST body：`{"mode":"standard\|full_speed\|optimal\|heavy_io"}`） |
| `duty` | GET / POST | 读取 / 设置指定区域转速（`?zone=0\|1`，POST body：`{"percent":0-100}`） |

### 使用的 IPMI 命令（Supermicro 私有）

```
ipmitool raw 0x30 0x45 0x00              # 读取风扇模式
ipmitool raw 0x30 0x45 0x01 <mode>       # 设置风扇模式
ipmitool raw 0x30 0x70 0x66 0x00 <zone>  # 读取区域转速
ipmitool raw 0x30 0x70 0x66 0x01 <zone> <pct>  # 设置区域转速
ipmitool sdr type Fan                    # 风扇 SDR
ipmitool sdr type Temp                   # 温度 SDR
```

## 注意事项

- 自定义转速需在 **Full Speed** 模式下生效
- 依赖 IPMI 通道可用（BMC 已启动、`ipmitool` 可正常通信）
- 详见 `LICENSE` 中的声明
