Ext.define('SYNO.SDS.IPMIFanControl.Instance', {
    extend: 'SYNO.SDS.AppInstance',
    appWindowName: 'SYNO.SDS.IPMIFanControl.Main',
    constructor: function() {
        this.callParent(arguments);
    }
});

Ext.define('SYNO.SDS.IPMIFanControl.Main', {
    extend: 'SYNO.SDS.AppWindow',
    appInstance: null,

    constructor: function(cfg) {
        this.appInstance = cfg.appInstance;

        var config = Ext.apply({
            resizable: true,
            maximizable: true,
            minimizable: true,
            width: 800,
            height: 600,
            minWidth: 640,
            minHeight: 480,
            layout: 'fit',
            items: [
                new Ext.BoxComponent({
                    height: '100%',
                    html: '<iframe title="IPMI风扇控制" src="/webman/3rdparty/IPMIFanControl/index.html" frameborder="0" width="100%" height="100%" style="display:block"></iframe>'
                })
            ]
        }, cfg);

        this.callParent([config]);
    }
});
