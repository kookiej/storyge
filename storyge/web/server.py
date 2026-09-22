"""로컬 서버를 띄운다."""

from __future__ import annotations

import socket
import threading
import webbrowser

from .. import config, i18n
from . import create_app

DEFAULT_PORT = 8760
# 포트가 물려 있으면 하나씩 올려 가며 찾는다
PORT_TRIES = 10


def _free_port(host: str, start: int) -> int:
    """비어 있는 포트를 찾는다. 다 막혀 있으면 그냥 start 를 돌려주고 Flask 가 알린다."""
    for offset in range(PORT_TRIES):
        candidate = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
        return candidate
    return start


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          open_browser: bool = True) -> int:
    cfg = config.load()
    i18n.set_lang(cfg.lang)

    port = _free_port(host, port)
    address = f"http://{host}:{port}/"

    print(f"Storyge 웹  {address}")
    print("멈추려면 Ctrl+C")

    if open_browser:
        threading.Timer(0.5, webbrowser.open, (address,)).start()

    app = create_app()
    # use_reloader=False: 리로더는 프로세스를 하나 더 띄우므로 작업이 두 벌 등록된다.
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
    return 0
