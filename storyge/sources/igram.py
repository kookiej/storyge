"""igram.world.

fastdl.app 과 같은 백엔드다 (/api/convert, /api/captcha, x-token 이 모두 같다).
동작은 convert_site.py 에 있다.
"""

from __future__ import annotations

from .convert_site import ConvertSite


class Igram(ConvertSite):
    host = "igram.world"
    id = "igram"
    label = "igram.world"
