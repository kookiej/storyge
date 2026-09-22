# -*- coding: utf-8 -*-
"""로고를 만든다. 결과물(logo.svg / logo.ico / logo.png)은 이 파일이 유일한 원본이다.

    .venv\\Scripts\\python.exe assets\\make_logo.py

모양: 인스타그램 스토리 링(그라데이션 원) 안에 내려받기 화살표. 배경은 투명하다.

**색은 theme.GRADIENT 에서 가져온다.** 여기에 hex 를 손으로 적으면 앱 화면의 링과
로고의 색이 조용히 어긋난다 (web/views.py 가 CSS 색을 팔레트에서 뽑아 쓰는 것과 같은 이유).

그라데이션은 **대각선 선형**이다. 인스타그램의 진짜 링은 원을 도는 각도 그라데이션이지만,
theme._diagonal_gradient 가 이미 같은 이유로 대각선으로 근사하고 있고 (보기에 거의 같다),
SVG 1.1 에는 각도 그라데이션이 아예 없다. 셋(로고 svg / 로고 ico / 앱의 링)을 같은 규칙으로
맞춰 두는 편이 낫다.

좌표는 1024 칸 기준이고 SVG 와 Pillow 가 **같은 숫자를 쓴다** — 두 벌로 두면 한쪽만 고치게 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storyge.theme import GRADIENT  # noqa: E402

HERE = Path(__file__).resolve().parent

# --- 모양 (1024 칸 기준) ---------------------------------------------
#
# 링은 바깥 반지름 480 (1024 칸에 32 여백) 에 두께 88. 아이콘용으로 진짜 스토리 링보다
# 도톰하게 잡았다 — 16px 파비콘까지 줄이면 얇은 링은 사라진다.
SIZE = 1024
CENTER = SIZE / 2
RING_OUTER = 480
RING_WIDTH = 88

# 화살표. 링 안쪽(반지름 392)에서 40 쯤 떼고, 꼭짓점이 전부 그 안에 들어오게 잡았다.
STEM_HALF = 50            # 기둥 반너비
STEM_TOP = 290
STEM_BOTTOM = 520
HEAD_HALF = 175           # 촉 반너비
HEAD_TOP = 470
HEAD_TIP = 675            # 아래 꼭짓점
TRAY_HALF = 195           # 받침 반너비
TRAY_TOP = 715
TRAY_BOTTOM = 770

# ico 에 넣을 크기들. 16 은 브라우저 탭과 탐색기 목록, 256 은 큰 아이콘 보기.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# 그라데이션이 흐르는 구간. **칸 전체가 아니라 링의 대각선**이다.
# 칸의 모서리(0,0)~(1024,1024)에 걸면 주황과 파랑이 그 모서리에만 있고 원은 거기까지
# 닿지 않아, 링에 분홍~보라만 남는다. 원이 실제로 지나는 45° 지점을 양 끝으로 잡아야
# 왼쪽 위가 주황, 오른쪽 아래가 파랑으로 제대로 돈다.
_REACH = RING_OUTER / (2 ** 0.5)
GRAD_FROM = CENTER - _REACH
GRAD_TO = CENTER + _REACH


# --- 그라데이션 ------------------------------------------------------

def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _at(position: float) -> tuple[int, int, int]:
    """0.0~1.0 위치의 색. theme._at 과 같은 계산이다."""
    position = min(max(position, 0.0), 1.0)
    span = position * (len(GRADIENT) - 1)
    index = min(int(span), len(GRADIENT) - 2)
    ratio = span - index
    start, end = _rgb(GRADIENT[index]), _rgb(GRADIENT[index + 1])
    return tuple(round(a + (b - a) * ratio) for a, b in zip(start, end))  # type: ignore[return-value]


def _diagonal(size: int) -> Image.Image:
    """왼쪽 위에서 오른쪽 아래로 흐르는 그라데이션.

    **마크 전체에 하나만 흐른다.** 화살표에 따로 한 벌을 더 입히면 16px 로 줄였을 때
    일곱 픽셀 안에 네 색이 들어가 뭉개진다. 하나로 흘려 두면 화살표는 가운데 색
    (분홍~보라) 하나로 또렷하게 남고, 링이 주황부터 파랑까지 다 보여 준다.
    """
    steps = 64
    # 45° 벡터에 내린 투영이라 (x + y) 하나로 위치가 정해진다.
    # SVG 와 같은 색이 나오도록 1024 칸의 좌표로 돌려 놓고 잰다.
    start = GRAD_FROM * 2
    span = (GRAD_TO - GRAD_FROM) * 2
    small = Image.new("RGB", (steps, steps))
    pixels = small.load()
    for y in range(steps):
        for x in range(steps):
            here = (x + y) * SIZE / (steps - 1)
            pixels[x, y] = _at((here - start) / span)
    return small.resize((size, size), Image.BICUBIC)


# --- 모양 그리기 -----------------------------------------------------

def _mask(scale: int) -> Image.Image:
    """링과 화살표를 합친 알파 마스크. 크게 그린 뒤 줄여서 계단을 없앤다."""
    big = SIZE * scale
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)

    def box(left, top, right, bottom):
        return (left * scale, top * scale, right * scale, bottom * scale)

    # 링 — 바깥 원을 채우고 안쪽을 도려낸다 (theme.gradient_border 와 같은 방법)
    outer = CENTER - RING_OUTER
    draw.ellipse(box(outer, outer, SIZE - outer, SIZE - outer), fill=255)
    inner = outer + RING_WIDTH
    draw.ellipse(box(inner, inner, SIZE - inner, SIZE - inner), fill=0)

    # 화살표 기둥 (양 끝이 둥근 막대)
    draw.rounded_rectangle(
        box(CENTER - STEM_HALF, STEM_TOP, CENTER + STEM_HALF, STEM_BOTTOM),
        radius=STEM_HALF * scale, fill=255,
    )
    # 화살촉
    draw.polygon(
        [
            ((CENTER - HEAD_HALF) * scale, HEAD_TOP * scale),
            ((CENTER + HEAD_HALF) * scale, HEAD_TOP * scale),
            (CENTER * scale, HEAD_TIP * scale),
        ],
        fill=255,
    )
    # 받침
    draw.rounded_rectangle(
        box(CENTER - TRAY_HALF, TRAY_TOP, CENTER + TRAY_HALF, TRAY_BOTTOM),
        radius=((TRAY_BOTTOM - TRAY_TOP) / 2) * scale, fill=255,
    )
    return mask.resize((SIZE, SIZE), Image.LANCZOS)


def render() -> Image.Image:
    """투명 배경 RGBA 로고 (1024x1024)."""
    logo = _diagonal(SIZE).convert("RGBA")
    logo.putalpha(_mask(scale=4))
    return logo


# --- SVG -------------------------------------------------------------

def svg() -> str:
    """벡터 원본. 웹이 이걸 그대로 쓴다 (파비콘과 왼쪽 위 마크).

    같은 좌표를 쓰므로 ico 와 모양이 어긋나지 않는다.
    """
    stops = "".join(
        f'\n      <stop offset="{i / (len(GRADIENT) - 1):.4f}" stop-color="{color}"/>'
        for i, color in enumerate(GRADIENT)
    )
    n = {                                     # 좌표를 짧은 글자로
        name: f"{value:g}" for name, value in {
            "size": SIZE, "c": CENTER,
            "from": GRAD_FROM, "to": GRAD_TO,
            "ring_r": RING_OUTER - RING_WIDTH / 2, "ring_w": RING_WIDTH,
            "stem_x": CENTER - STEM_HALF, "stem_y": STEM_TOP,
            "stem_w": STEM_HALF * 2, "stem_h": STEM_BOTTOM - STEM_TOP,
            "head_l": CENTER - HEAD_HALF, "head_r": CENTER + HEAD_HALF,
            "head_y": HEAD_TOP, "head_tip": HEAD_TIP,
            "tray_x": CENTER - TRAY_HALF, "tray_y": TRAY_TOP,
            "tray_w": TRAY_HALF * 2, "tray_h": TRAY_BOTTOM - TRAY_TOP,
            "tray_r": (TRAY_BOTTOM - TRAY_TOP) / 2,
            "stem_r": STEM_HALF,
        }.items()
    }

    # gradientUnits 는 반드시 userSpaceOnUse. 기본값(objectBoundingBox)으로 두면
    # 그라데이션이 **도형마다 따로** 잡혀 화살표 하나에 네 색이 전부 들어간다.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n['size']} {n['size']}"
     width="{n['size']}" height="{n['size']}" role="img" aria-label="Storyge">
  <!-- assets/make_logo.py 가 만든다. 손으로 고치지 말 것. -->
  <defs>
    <linearGradient id="storyge-ring" gradientUnits="userSpaceOnUse"
                    x1="{n['from']}" y1="{n['from']}" x2="{n['to']}" y2="{n['to']}">{stops}
    </linearGradient>
  </defs>
  <g fill="url(#storyge-ring)">
    <circle cx="{n['c']}" cy="{n['c']}" r="{n['ring_r']}"
            fill="none" stroke="url(#storyge-ring)" stroke-width="{n['ring_w']}"/>
    <rect x="{n['stem_x']}" y="{n['stem_y']}" width="{n['stem_w']}" height="{n['stem_h']}"
          rx="{n['stem_r']}"/>
    <path d="M {n['head_l']} {n['head_y']} H {n['head_r']} L {n['c']} {n['head_tip']} Z"/>
    <rect x="{n['tray_x']}" y="{n['tray_y']}" width="{n['tray_w']}" height="{n['tray_h']}"
          rx="{n['tray_r']}"/>
  </g>
</svg>
"""


# --- 내보내기 --------------------------------------------------------

def main() -> int:
    logo = render()

    png = HERE / "logo.png"
    logo.save(png)

    # exe 아이콘. 작은 크기는 Pillow 가 LANCZOS 로 줄여 넣는다.
    ico = HERE / "logo.ico"
    logo.save(ico, format="ICO", sizes=[(n, n) for n in ICO_SIZES])

    vector = HERE / "logo.svg"
    vector.write_text(svg(), encoding="utf-8")

    for path in (vector, ico, png):
        print(f"{path.name:>10}  {path.stat().st_size / 1024:6.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
