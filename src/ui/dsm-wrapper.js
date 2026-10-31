// DSM 桌面应用窗口注册（浮窗机制）。
// 只有 ui/config 的 ".url" 条目时，DSM 只会用新浏览器页面打开 URL；
// 要在 DSM 桌面上开出可调大小/可最大化的原生应用窗口，必须在此以
// Ext JS 定义 SYNO.SDS.AppInstance / SYNO.SDS.AppWindow 两个类：
//   - INFO 的 dsmappname = AppInstance 类名（DSM 应用加载器据此解析）
//   - ui/config 中以本文件名为节键（"dsm-wrapper.js"）声明这两个类
// 窗口内容为 iframe，加载 DSM 托管的套件页面（与 DSM 同源，API 直接走 api.cgi）。
// 结构与 IP-Monitor-DSM 保持一致（同源项目，同一套窗口骨架）。
Ext.ns('MeowPerth.IPMIFanControl');

Ext.define('MeowPerth.IPMIFanControl.AppInstance', {
    extend: 'SYNO.SDS.AppInstance',
    appWindowName: 'MeowPerth.IPMIFanControl.AppWindow',
    constructor: function () {
        this.callParent(arguments);
    },
});

Ext.define('MeowPerth.IPMIFanControl.AppWindow', {
    extend: 'SYNO.SDS.AppWindow',
    constructor: function (config) {
        const cfg = Ext.apply(
            {
                resizable: true,
                maximizable: true,
                minimizable: true,
                width: 1000,
                height: 680,
                minWidth: 620,
                minHeight: 460,
                layout: 'fit',
                border: false,
                cls: 'syno-app-ipmifancontrol-wrapper',
                items: [
                    {
                        xtype: 'box',
                        autoEl: {
                            tag: 'iframe',
                            src: '/webman/3rdparty/ipmifancontrol/index.html',
                            frameborder: '0',
                            style: 'width:100%; height:100%; border:none;',
                        },
                    },
                ],
            },
            config
        );
        this.callParent([cfg]);
    },
    onOpen: function (info) {
        this.callParent([info]);
    },
    onRequest: function (info) {
        this.onOpen(info);
    },
});
