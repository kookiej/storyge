"""화면 색과 그라데이션 링.

exe 두 개가 같은 코드를 쓰되 겉모습만 다르게 하기 위한 모듈이다.

  - "classic" : 지금까지의 tkinter 기본 모양. 색을 건드리지 않는다(값이 None).
  - "dark" / "light" : 인스타그램 앱의 디자인 언어를 참고한 화면.

색을 쓰는 쪽은 palette()[키] 를 읽고, 값이 None 이면 그 위젯의 색을 지정하지 않는다.
그래야 classic 에서 기존 모양이 그대로 유지된다.

인스타그램의 로고·워드마크·아이콘 자산은 쓰지 않는다. 색과 배치만 참고한 것이다.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Optional

from PIL import Image, ImageDraw

FONT = ("Malgun Gothic", 10)
FONT_BOLD = ("Malgun Gothic", 10, "bold")
FONT_TITLE = ("Malgun Gothic", 14, "bold")
FONT_SMALL = ("Malgun Gothic", 8)

# 진행 상황 로그창 폰트.
# classic 이 쓰던 Consolas 에는 한글 글리프가 없어 윈도우가 대체 폰트로 그린다.
# 그래서 색 테마에서는 한글이 제대로 있는 Malgun Gothic 을 쓴다.
LOG_FONTS = {
    "classic": ("Consolas", 9),
    "dark": ("Malgun Gothic", 9),
    "light": ("Malgun Gothic", 9),
}

# 스토리 링의 주황 -> 핑크 -> 보라 흐름을 참고한 색
GRADIENT = ("#F58529", "#DD2A7B", "#8134AF", "#515BD4")

# 모든 팔레트는 같은 키를 가져야 한다. (키가 빠지면 실행 중에 KeyError 로 터진다)
_KEYS = (
    "bg", "surface", "surface_alt", "border", "text", "text_dim",
    "accent", "accent_hover", "hover", "danger",
    "list_select_bg", "list_select_fg",
    "cell_border_off", "cell_border_on", "cell_bg_on", "thumb_fail_bg",
)

PALETTES: dict[str, dict[str, Optional[str]]] = {
    # 값이 None = "건드리지 말고 tkinter 기본값을 써라"
    "classic": {
        "bg": None,
        "surface": None,
        "surface_alt": None,
        "border": None,
        "text": None,
        "text_dim": None,
        "accent": None,
        "accent_hover": None,
        "hover": None,
        "danger": None,
        "list_select_bg": None,
        "list_select_fg": None,
        # 선택 창에 원래 박혀 있던 값 그대로
        "cell_border_off": "#c8c8c8",
        "cell_border_on": "#0a84ff",
        "cell_bg_on": "#dbeafe",
        "thumb_fail_bg": "#e5e5e5",
    },
    "dark": {
        "bg": "#000000",
        "surface": "#121212",
        "surface_alt": "#1A1A1A",
        "border": "#262626",
        "text": "#FAFAFA",
        "text_dim": "#A8A8A8",
        "accent": "#0095F6",
        "accent_hover": "#1AA1FF",
        "hover": "#262626",
        "danger": "#ED4956",
        "list_select_bg": "#262626",
        "list_select_fg": "#FAFAFA",
        "cell_border_off": "#262626",
        "cell_border_on": "#DD2A7B",
        "cell_bg_on": "#1A1A1A",
        "thumb_fail_bg": "#1A1A1A",
    },
    "light": {
        "bg": "#FFFFFF",
        "surface": "#FFFFFF",
        "surface_alt": "#FAFAFA",
        "border": "#DBDBDB",
        "text": "#262626",
        "text_dim": "#8E8E8E",
        "accent": "#0095F6",
        "accent_hover": "#1AA1FF",
        "hover": "#EFEFEF",
        "danger": "#ED4956",
        "list_select_bg": "#EFEFEF",
        "list_select_fg": "#262626",
        "cell_border_off": "#DBDBDB",
        "cell_border_on": "#DD2A7B",
        "cell_bg_on": "#FAFAFA",
        "thumb_fail_bg": "#EFEFEF",
    },
}

_current = "classic"


def set_theme(theme_name: str) -> None:
    global _current
    _current = theme_name if theme_name in PALETTES else "classic"


def name() -> str:
    return _current


def palette() -> dict[str, Optional[str]]:
    return PALETTES[_current]


def color(key: str) -> Optional[str]:
    """색 하나. None 이면 '지정하지 말 것'."""
    return PALETTES[_current][key]


def is_styled() -> bool:
    """classic 이 아니면 True — 색을 입혀도 되는 상태."""
    return _current != "classic"


def log_font() -> tuple:
    """진행 상황 로그창에 쓸 폰트. 색이 아니라 별도로 둔다."""
    return LOG_FONTS[_current]


def other_theme() -> str:
    """토글 버튼이 넘어갈 반대편 테마."""
    return "light" if _current == "dark" else "dark"


# --- ttk 스타일 -----------------------------------------------------


def apply(root) -> None:
    """ttk 위젯 전반에 색을 입힌다. classic 이면 아무것도 하지 않는다.

    Windows 기본 ttk 테마(vista)는 background 지정을 대부분 무시하므로
    반드시 clam 으로 바꾼 뒤에 색을 지정해야 한다.
    """
    if not is_styled():
        return

    p = palette()
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=p["bg"])

    style.configure(
        ".",
        background=p["bg"],
        foreground=p["text"],
        fieldbackground=p["surface_alt"],
        bordercolor=p["border"],
        lightcolor=p["border"],
        darkcolor=p["border"],
        troughcolor=p["surface_alt"],
        focuscolor=p["accent"],
        font=FONT,
    )

    style.configure("TFrame", background=p["bg"])
    style.configure("Card.TFrame", background=p["surface"])

    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Card.TLabel", background=p["surface"], foreground=p["text"])
    style.configure("Dim.TLabel", background=p["surface"], foreground=p["text_dim"], font=FONT_SMALL)
    style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=FONT_TITLE)
    style.configure("Sub.TLabel", background=p["bg"], foreground=p["text_dim"], font=FONT_SMALL)
    style.configure("Head.TLabel", background=p["surface"], foreground=p["text_dim"], font=FONT_BOLD)

    # 인스타그램 버튼은 테두리 없이 평평하다
    style.configure(
        "TButton",
        background=p["surface_alt"],
        foreground=p["text"],
        borderwidth=0,
        focusthickness=0,
        padding=(12, 7),
        font=FONT,
    )
    style.map(
        "TButton",
        background=[("disabled", p["surface"]), ("pressed", p["border"]), ("active", p["hover"])],
        foreground=[("disabled", p["text_dim"])],
    )

    style.configure("Accent.TButton", background=p["accent"], foreground="#FFFFFF", font=FONT_BOLD)
    style.map(
        "Accent.TButton",
        background=[("disabled", p["surface_alt"]), ("pressed", p["accent"]), ("active", p["accent_hover"])],
        foreground=[("disabled", p["text_dim"])],
    )

    style.configure(
        "TEntry",
        fieldbackground=p["surface_alt"],
        foreground=p["text"],
        insertcolor=p["text"],
        borderwidth=0,
        padding=6,
    )
    style.map("TEntry", fieldbackground=[("readonly", p["surface_alt"])])

    # 콤보 상자(반복 방식 고르기). 펼쳐지는 목록은 ttk 가 아니라 tk 리스트박스라
    # 스타일이 닿지 않는다 — option_add 로 따로 색을 준다.
    style.configure(
        "TCombobox",
        fieldbackground=p["surface_alt"],
        background=p["surface_alt"],
        foreground=p["text"],
        arrowcolor=p["text_dim"],
        borderwidth=0,
        padding=5,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p["surface_alt"])],
        foreground=[("readonly", p["text"])],
        background=[("readonly", p["surface_alt"]), ("active", p["hover"])],
        selectbackground=[("readonly", p["surface_alt"])],
        selectforeground=[("readonly", p["text"])],
    )
    root.option_add("*TCombobox*Listbox.background", p["surface_alt"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    # clam 의 체크/라디오 표시는 indicatorcolor 가 아니라
    # **indicatorbackground(원판) 과 indicatorforeground(안의 점·체크)** 를 받는다.
    # 기본 원판이 흰색이라, 그대로 두면 어두운 화면에서 고른 것과 안 고른 것이
    # 둘 다 흰 동그라미로 보여 어느 쪽이 골라졌는지 읽히지 않는다.
    # 원판을 입력칸과 같은 어두운 색으로 깔고, 고르면 강조색 점이 찍히게 한다.
    for widget in ("TCheckbutton", "TRadiobutton"):
        style.configure(
            widget,
            background=p["bg"], foreground=p["text"], focuscolor=p["bg"],
            indicatorbackground=p["surface_alt"],
            indicatorforeground=p["accent"],
            upperbordercolor=p["border"], lowerbordercolor=p["border"],
        )
        style.map(
            widget,
            background=[("active", p["bg"])],
            indicatorbackground=[("disabled", p["surface"]), ("selected", p["surface_alt"])],
            indicatorforeground=[("disabled", p["text_dim"]), ("selected", p["accent"])],
        )
    style.configure("Card.TCheckbutton", background=p["surface"], foreground=p["text"])
    style.map("Card.TCheckbutton", background=[("active", p["surface"])])

    # 세로/가로 스크롤바는 별도 스타일 이름을 쓰므로 셋 다 지정해야 확실히 먹는다.
    # (thumb 색은 background, 배경 홈은 troughcolor. light/darkcolor 까지 맞춰야
    #  clam 의 입체 테두리가 밝게 남지 않는다)
    for scrollbar_style in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            background=p["border"],
            troughcolor=p["surface_alt"],
            bordercolor=p["surface_alt"],
            lightcolor=p["border"],
            darkcolor=p["border"],
            arrowcolor=p["text_dim"],
            borderwidth=0,
            relief="flat",
            width=12,
        )
        style.map(
            scrollbar_style,
            background=[("pressed", p["text_dim"]), ("active", p["text_dim"])],
        )


# --- 그라데이션 링 --------------------------------------------------


def _mix(color_a: str, color_b: str, ratio: float) -> tuple[int, int, int]:
    a = tuple(int(color_a[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(round(x + (y - x) * ratio) for x, y in zip(a, b))  # type: ignore[return-value]


def mix_hex(color_a: str, color_b: str, ratio: float) -> str:
    """두 색 사이를 오가는 색. 토글 스위치 애니메이션에서 쓴다."""
    r, g, b = _mix(color_a, color_b, min(max(ratio, 0.0), 1.0))
    return f"#{r:02x}{g:02x}{b:02x}"


def _at(position: float, colors=GRADIENT) -> tuple[int, int, int]:
    """0.0~1.0 위치의 색."""
    position = min(max(position, 0.0), 1.0)
    span = position * (len(colors) - 1)
    index = min(int(span), len(colors) - 2)
    return _mix(colors[index], colors[index + 1], span - index)


def _diagonal_gradient(width: int, height: int, colors=GRADIENT) -> Image.Image:
    """대각선 방향 그라데이션.

    작은 이미지에 색을 채운 뒤 확대하는 방식이라 픽셀마다 계산하지 않아 빠르다.
    (인스타그램의 링은 원을 도는 각도 그라데이션이지만, 대각선 선형으로도
     보기에 거의 같고 구현이 훨씬 단순해서 의도적으로 근사했다)
    """
    steps = 48
    small = Image.new("RGB", (steps, steps))
    pixels = small.load()
    for y in range(steps):
        for x in range(steps):
            pixels[x, y] = _at((x + y) / (2 * (steps - 1)), colors)
    return small.resize((max(width, 1), max(height, 1)), Image.BICUBIC)


def gradient_border(
    width: int,
    height: int,
    thickness: int = 4,
    radius: int = 12,
    circular: bool = False,
    colors=GRADIENT,
) -> Image.Image:
    """테두리만 남긴 그라데이션 이미지(RGBA). 가운데는 완전히 투명하다.

    tkinter 는 둥근 모서리도 그라데이션도 못 그리므로 Pillow 로 만들어 붙인다.
    4배로 그린 뒤 줄여서 가장자리 계단을 없앤다.
    """
    scale = 4
    big_w, big_h = width * scale, height * scale
    big_t, big_r = thickness * scale, radius * scale

    gradient = _diagonal_gradient(big_w, big_h, colors).convert("RGBA")

    # 바깥 도형을 채우고 안쪽을 도려내 테두리 모양의 마스크를 만든다
    mask = Image.new("L", (big_w, big_h), 0)
    draw = ImageDraw.Draw(mask)
    outer = (0, 0, big_w - 1, big_h - 1)
    inner = (big_t, big_t, big_w - 1 - big_t, big_h - 1 - big_t)
    if circular:
        draw.ellipse(outer, fill=255)
        draw.ellipse(inner, fill=0)
    else:
        draw.rounded_rectangle(outer, radius=big_r, fill=255)
        draw.rounded_rectangle(inner, radius=max(big_r - big_t, 0), fill=0)

    gradient.putalpha(mask)
    return gradient.resize((width, height), Image.LANCZOS)


def round_corners(image: Image.Image, radius: int) -> Image.Image:
    """모서리를 둥글게 깎은 RGBA 이미지.

    링은 모서리가 둥근데 사진은 각져 있으면 네 귀퉁이가 어긋나 보인다.
    그래서 사진 쪽도 같은 반지름으로 깎아 준다.
    """
    scale = 4
    width, height = image.size
    mask = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1), radius=radius * scale, fill=255
    )
    result = image.convert("RGBA")
    result.putalpha(mask.resize((width, height), Image.LANCZOS))
    return result


def framed(
    thumb: Image.Image,
    thickness: int = 3,
    gap: int = 0,
    radius: int = 10,
    ring: bool = True,
) -> Image.Image:
    """썸네일에 여백을 두른 이미지. ring=True 면 그라데이션 테두리를 얹는다.

    고른 것과 안 고른 것의 크기가 같아야 칸이 움찔거리지 않으므로,
    두 경우 모두 이 함수로 만들어 같은 여백을 준다.
    """
    pad = thickness + gap
    width, height = thumb.width + pad * 2, thumb.height + pad * 2

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(round_corners(thumb, radius), (pad, pad))
    if ring:
        canvas.alpha_composite(gradient_border(width, height, thickness=thickness, radius=radius + pad))
    return canvas


def with_ring(
    thumb: Image.Image,
    thickness: int = 3,
    gap: int = 0,
    radius: int = 10,
) -> Image.Image:
    """썸네일 둘레에 그라데이션 테두리를 두른 새 이미지."""
    return framed(thumb, thickness=thickness, gap=gap, radius=radius, ring=True)


def ring_badge(size: int = 32, thickness: int = 3, fill: Optional[str] = None) -> Image.Image:
    """계정 이름 앞에 붙이는 작은 원형 링."""
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if fill:
        ImageDraw.Draw(badge).ellipse(
            (thickness + 1, thickness + 1, size - thickness - 2, size - thickness - 2), fill=fill
        )
    badge.alpha_composite(gradient_border(size, size, thickness=thickness, circular=True))
    return badge
