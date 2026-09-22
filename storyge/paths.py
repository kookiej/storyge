"""데이터 파일 경로를 한 곳에서만 계산한다.

다른 모듈은 경로를 직접 조립하지 말고 여기의 상수를 쓴다.
data 폴더에는 로그인 세션이 들어가므로 .gitignore 로 제외되어 있다.

exe(PyInstaller onefile)로 실행할 때 주의:
  onefile 은 코드를 임시 폴더에 풀었다가 종료할 때 지운다. 따라서 __file__ 기준으로
  경로를 잡으면 설정과 세션이 매번 사라진다. exe 일 때는 exe 가 놓인 폴더를 쓴다.
"""

import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # exe 로 실행 중 — exe 파일이 놓인 폴더 옆에 data 를 둔다
        return Path(sys.executable).resolve().parent
    # 평소처럼 파이썬으로 실행 중 — 프로젝트 폴더
    return Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """data 폴더 위치. 환경변수로 덮어쓸 수 있다.

    exe 는 exe 옆, 소스 실행은 프로젝트 폴더가 기본이다. 그런데 둘을 같이 쓰면
    **서로 다른 폴더를 보게 된다** — exe 로 로그인해도 소스로 띄운 웹은 그 세션을
    못 찾는다. STORYGE_DATA 를 주면 양쪽을 한 곳으로 모을 수 있다.
    """
    override = os.environ.get("STORYGE_DATA", "").strip()
    if override:
        return Path(override).expanduser()
    return _base_dir() / "data"


def _asset_dir() -> Path:
    """로고처럼 **프로그램에 딸려 오는 읽기 전용 파일**이 있는 곳.

    data 폴더와 규칙이 다르다. onefile exe 는 번들을 임시 폴더(sys._MEIPASS)에 풀었다가
    지우는데, 로고는 거기 있고 exe 옆에는 없다. 반대로 설정과 세션은 지워지면 안 되니
    exe 옆을 쓴다 (_base_dir). 그래서 둘을 따로 잡는다.
    """
    bundled = getattr(sys, "_MEIPASS", "")
    if bundled:
        return Path(bundled) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


BASE_DIR = _base_dir()
DATA_DIR = _default_data_dir()

# 로고. assets/make_logo.py 가 만든다. 창 아이콘과 exe 아이콘, 웹 파비콘이 같은 그림을 쓴다.
ASSET_DIR = _asset_dir()
LOGO_ICO = ASSET_DIR / "logo.ico"
LOGO_SVG = ASSET_DIR / "logo.svg"
LOGO_PNG = ASSET_DIR / "logo.png"

# 로그인 정보(세션·자격증명)를 둔 곳. 기본은 data 폴더와 같다.
# 웹은 여기만 exe 와 함께 쓰고 설정·기록은 자기 것을 쓴다 (use_login_dir 참고).
LOGIN_DIR = DATA_DIR

CONFIG_FILE = DATA_DIR / "config.json"
# instagrapi 의 세션 형식(JSON). 예전 instaloader 세션(pickle)과 호환되지 않아 이름을 바꿨다.
SESSION_FILE = LOGIN_DIR / "session.json"
DOWNLOADED_FILE = DATA_DIR / "downloaded.json"
# 윈도우 DPAPI 로 암호화한 아이디/비밀번호. 세션이 만료됐을 때 다시 로그인하는 데 쓴다.
CREDENTIAL_FILE = LOGIN_DIR / "credential.bin"

# 예약 수집이 모아 둔 스토리 (원본 + 썸네일 + index.json)
STAGING_DIR = DATA_DIR / "staging"
STAGING_INDEX = STAGING_DIR / "index.json"
# 창 없이 도는 예약 실행의 기록. 창이 없어 결과를 볼 방법이 이것뿐이다.
SCHEDULE_LOG = DATA_DIR / "schedule.log"
# 지금/마지막 수집의 진행 상태. 창(GUI)과 창 없는 예약 실행이 같이 본다.
RUN_STATE = DATA_DIR / "run_state.json"
# 이 파일이 있으면 창 없는 예약 실행이 다음 계정으로 넘어가기 전에 멈춘다.
CANCEL_FLAG = DATA_DIR / "cancel.flag"


def ensure_staging_dir() -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_DIR


def ensure_data_dir() -> Path:
    """data 폴더가 없으면 만들고 경로를 돌려준다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def use_data_dir(path) -> Path:
    """data 폴더를 다른 곳으로 옮긴다. **다른 모듈을 쓰기 전에** 불러야 한다.

    다른 모듈은 전부 `paths.CONFIG_FILE` 처럼 **부를 때마다** 여기를 읽으므로,
    여기 상수만 바꿔 놓으면 그 뒤의 모든 읽기·쓰기가 새 폴더로 간다.
    (테스트가 임시 폴더로 돌려놓는 방식과 같다.)

    로그인 폴더도 같이 옮긴다. 따로 두려면 이것을 부른 **뒤에** use_login_dir 을 부른다.
    """
    global DATA_DIR, CONFIG_FILE, DOWNLOADED_FILE
    global STAGING_DIR, STAGING_INDEX, SCHEDULE_LOG, RUN_STATE, CANCEL_FLAG

    DATA_DIR = Path(path).expanduser()
    CONFIG_FILE = DATA_DIR / "config.json"
    DOWNLOADED_FILE = DATA_DIR / "downloaded.json"
    STAGING_DIR = DATA_DIR / "staging"
    STAGING_INDEX = STAGING_DIR / "index.json"
    SCHEDULE_LOG = DATA_DIR / "schedule.log"
    RUN_STATE = DATA_DIR / "run_state.json"
    CANCEL_FLAG = DATA_DIR / "cancel.flag"
    use_login_dir(DATA_DIR)
    return DATA_DIR


def use_login_dir(path) -> Path:
    """로그인 정보(세션·자격증명)만 다른 폴더에서 쓴다.

    웹이 exe 의 로그인을 빌려 쓰되 **설정과 기록은 섞지 않으려고** 있다.
    exe 로 한 번 로그인해 두면 웹도 그 세션을 쓰고, 계정 목록·저장 폴더·저장 기록은
    각자 자기 폴더 것을 본다.
    """
    global LOGIN_DIR, SESSION_FILE, CREDENTIAL_FILE

    LOGIN_DIR = Path(path).expanduser()
    SESSION_FILE = LOGIN_DIR / "session.json"
    CREDENTIAL_FILE = LOGIN_DIR / "credential.bin"
    return LOGIN_DIR


def looks_like_data_dir(path) -> bool:
    """이미 쓰고 있는 data 폴더처럼 보이는가 (설정이나 세션이 들어 있는가)."""
    folder = Path(path)
    return any((folder / name).exists()
               for name in ("config.json", "session.json", "downloaded.json"))
