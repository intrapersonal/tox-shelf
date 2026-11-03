def _shelf(par):
    ext = getattr(parent().ext, "ShelfExt", None)
    if ext is not None:
        ext.OnPar(par)


def onValueChange(par, prev):
    _shelf(par)


def onPulse(par):
    _shelf(par)


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
