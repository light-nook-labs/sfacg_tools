def run_pc():
    from .pc import run_pc as _run_pc
    _run_pc()


def run_mobile(target='app'):
    from .mobile import run_mobile as _run_mobile
    _run_mobile(target)


def run_web(host='127.0.0.1', port=8888):
    from .web import run_web as _run_web
    _run_web(host, port)
