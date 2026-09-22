"""fastdl.app.

실제 동작은 전부 convert_site.py 에 있다 — igram.world 와 같은 백엔드라서,
고칠 곳을 두 벌로 두면 한쪽만 고치고 다른 쪽을 잊게 된다.
"""

from __future__ import annotations

from .convert_site import ConvertSite


class Fastdl(ConvertSite):
    host = "fastdl.app"
    id = "fastdl"
    label = "fastdl.app"
