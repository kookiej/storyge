"""화면 한 장을 내려보낸다.

색은 theme.PALETTES 를 그대로 CSS 변수로 바꿔 쓴다 — CSS 파일에 hex 를 손으로
옮겨 적으면 exe 와 웹의 색이 조용히 어긋난다.
"""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import config, i18n, theme

bp = Blueprint("views", __name__)

# 웹은 '스타일' 제품만 있다. classic 은 exe 전용이라 여기 오지 않는다.
WEB_THEMES = ("dark", "light")


def css_palettes() -> dict[str, dict[str, str]]:
    """{"dark": {"bg": "#000000", "surface-alt": "#1A1A1A", ...}, "light": {...}}"""
    out: dict[str, dict[str, str]] = {}
    for name in WEB_THEMES:
        out[name] = {
            key.replace("_", "-"): value
            for key, value in theme.PALETTES[name].items()
            if value
        }
    return out


@bp.get("/")
def index():
    cfg = config.load()
    lang = cfg.lang if cfg.lang in i18n.LANGUAGES else "ko"
    return render_template(
        "index.html",
        palettes=css_palettes(),
        gradient=theme.GRADIENT,
        current_theme=cfg.theme if cfg.theme in WEB_THEMES else "dark",
        lang=lang,
        # 한국어 원문이 곧 키다. 없는 키는 클라이언트에서도 한국어 원문으로 떨어진다
        # (i18n.t 와 같은 규칙).
        #
        # 지금 언어가 무엇이든 **대응표는 늘 내려보낸다.** 그래야 언어를 바꿀 때
        # 새로고침 없이 그 자리에서 다시 칠할 수 있다 — 새로고침하면 돌던 수집이
        # 멈추고 격자와 선택이 날아간다. 어느 표를 쓸지는 window.LANG 이 정한다.
        i18n_table=i18n.EN,
    )
