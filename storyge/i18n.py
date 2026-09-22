"""한국어 / 영어 전환.

**한국어 문장을 그대로 키로 쓴다.** 'btn.fetch' 같은 별도 키를 만들면 부르는 곳을
전부 새 이름으로 바꿔야 하고, 번역이 빠졌을 때 화면에 키가 그대로 노출된다.
한국어를 키로 두면 표에 없는 문장은 자연스럽게 한국어로 되돌아간다.

값이 끼어드는 문장은 **이름 있는 자리표시자**를 쓴다. 한국어와 영어의 어순이 달라
위치 기반({0})으로는 옮길 수 없기 때문이다.

    t("추가함: {names}", names="@a, @b")
"""

from __future__ import annotations

LANGUAGES = ("ko", "en")

EN = {
    # --- 창 공통 -----------------------------------------------------
    "  인스타그램 스토리 저장": "  Instagram story saver",
    "저장 폴더": "Save folder",
    "계정": "Accounts",
    "진행 상황": "Progress",
    "확인": "Confirm",
    "취소": "Cancel",
    "완료": "Done",
    "폴더 선택": "Choose folder",
    "추가": "Add",
    "즐겨찾기": "Favorite",
    "로그인": "Log in",
    "로그인 안 됨": "Not logged in",
    "(아직 정하지 않음)": "(not set yet)",

    # --- 계정 카드 ---------------------------------------------------
    "즐겨찾기 켜기/끄기": "Toggle favorite",
    "선택 삭제": "Delete selected",
    "전체 선택": "Select all",
    "전체 해제": "Clear selection",
    "삭제 전 확인": "Ask before delete",
    "(여러 개 선택 가능)": "(multiple selection allowed)",
    "여러 개는 띄어쓰기로 구분하세요.  예)  abc def ghi   /   @abc   /   프로필 URL":
        "Separate multiple entries with spaces.  e.g.  abc def ghi   /   @abc   /   profile URL",
    "추가함: {names}": "Added: {names}",
    "이미 등록돼 있음: {names}": "Already registered: {names}",
    "삭제함: {names}": "Deleted: {names}",
    "즐겨찾기 변경: {names}": "Favorites changed: {names}",
    "선택 없음": "Nothing selected",
    "삭제할 계정을 목록에서 고르세요.": "Choose the accounts to delete from the list.",
    "즐겨찾기를 바꿀 계정을 목록에서 고르세요.":
        "Choose the accounts whose favorite state you want to change.",
    "삭제 확인": "Confirm deletion",
    "{count}개 계정을 목록에서 삭제할까요?\n\n{names}\n\n(이미 저장한 파일은 지워지지 않습니다)":
        "Delete {count} account(s) from the list?\n\n{names}\n\n"
        "(Files you already saved will not be removed.)",

    # --- 실행 줄 -----------------------------------------------------
    "전체 계정": "All accounts",
    "즐겨찾기만": "Favorites only",
    "선택한 계정만": "Selected only",
    "스토리 가져오기": "Fetch stories",
    "계정 없음": "No accounts",
    "즐겨찾기로 등록된 계정이 없습니다.": "No accounts are marked as favorites.",
    "등록된 계정이 없습니다.\n먼저 계정을 추가하세요.":
        "No accounts registered.\nAdd an account first.",
    "목록에서 가져올 계정을 고르세요.": "Choose the accounts to fetch from the list.",
    "저장 폴더 필요": "Save folder required",
    "먼저 저장 폴더를 정해 주세요.": "Please choose a save folder first.",
    "스토리를 저장할 폴더 선택": "Choose a folder to save stories in",
    "저장 폴더: {path}": "Save folder: {path}",

    # --- 진행 상황 ---------------------------------------------------
    "준비됐습니다. 저장 폴더와 계정을 확인한 뒤 '스토리 가져오기'를 누르세요.":
        "Ready. Check the save folder and accounts, then press 'Fetch stories'.",
    "설정 위치: {path}": "Settings location: {path}",
    "확인 중...": "Checking...",
    "로그인 중...": "Logging in...",
    "로그인 확인 중...": "Checking login...",
    "스토리 확인 중...": "Checking stories...",
    "고르는 중...": "Selecting...",
    "로그인됨: @{user}": "Logged in: @{user}",
    "스토리 확인 중: {names}": "Checking stories: {names}",
    "새 스토리 {count}개를 찾았습니다.": "Found {count} new stories.",
    "새로 저장할 스토리가 없습니다.": "No new stories to save.",
    "선택한 항목이 없습니다. (저장된 파일 없음)": "Nothing was selected. (No files saved.)",
    "{count}개 저장 중...": "Saving {count}...",
    "{count}개를 {folder} 에 저장합니다.": "Saving {count} item(s) to {folder}.",
    "완료: {ok}개 저장, {failed}개 실패": "Done: {ok} saved, {failed} failed",
    "{ok}개를 저장했습니다.\n실패 {failed}개.": "Saved {ok} item(s).\n{failed} failed.",
    "썸네일 불러오는 중... {done}/{total}": "Loading thumbnails... {done}/{total}",
    "오류가 생겼습니다: {reason}": "Something went wrong: {reason}",
    "  자세한 내용을 남겼습니다: {path}": "  Details were written to: {path}",
    "저장된 로그인 정보를 지웠습니다.": "Saved login info has been cleared.",

    # --- 로그인 창 ---------------------------------------------------
    "인스타그램 로그인": "Instagram login",
    "스토리를 가져오려면 로그인이 필요합니다.\n한 번만 하면 세션이 저장되어 다음부터는 묻지 않습니다.":
        "Logging in is required to fetch stories.\n"
        "Do it once and the session is saved, so you won't be asked again.",
    "아이디": "ID",
    "비밀번호": "Password",
    "입력 필요": "Input required",
    "아이디와 비밀번호를 모두 입력하세요.": "Enter both your ID and password.",
    "로그인 정보 초기화": "Reset login info",
    "이 PC 에 저장된 로그인 정보를 지울까요?\n다음 실행부터 다시 입력해야 합니다.":
        "Clear the login info saved on this PC?\nYou will have to enter it again next time.",
    "2단계 인증": "Two-factor authentication",
    "인증 앱 또는 문자로 받은 코드를 입력하세요.":
        "Enter the code from your authenticator app or text message.",

    # --- 선택 창 -----------------------------------------------------
    "저장할 스토리 선택": "Choose stories to save",
    "항목을 클릭해서 선택하세요.": "Click the items you want.",
    "이 계정 전체 선택": "Select all from this account",
    "저장": "Save",
    "지울 스토리 선택": "Choose stories to delete",
    "지우기": "Delete",
    "{count}개": "{count}",
    "{done} / {total}개 선택됨": "{done} of {total} selected",
    "(미리보기 실패)": "(preview failed)",

    # --- 로그인 / 세션 (session.py) ----------------------------------
    "인스타그램이 요청을 잠시 막았습니다. 몇 분에서 몇 시간 뒤에 다시 시도해 주세요.\n"
    "짧은 간격으로 여러 번 실행하면 이 상태가 길어집니다.":
        "Instagram has temporarily blocked requests. Try again in a few minutes to a few hours.\n"
        "Running it repeatedly in quick succession makes this last longer.",
    "인스타그램 로그인 상태 확인 중...": "Checking Instagram login...",
    "{message} (윈도우 오류 코드 0x{code})": "{message} (Windows error code 0x{code})",
    "  저장된 세션으로 로그인됨 (@{user})": "  Logged in with the saved session (@{user})",
    "  저장된 세션이 만료되었습니다.": "  The saved session has expired.",
    "  저장된 세션을 읽지 못했습니다: {reason}": "  Could not read the saved session: {reason}",
    "  로그인 확인 요청이 실패했지만 저장된 세션을 그대로 씁니다 (@{user})":
        "  The login check failed, but the saved session will be used anyway (@{user})",
    "    이유: {reason}": "    Reason: {reason}",
    "  저장된 로그인 정보로 다시 로그인합니다 (@{user})":
        "  Logging in again with the saved credentials (@{user})",
    "  2단계 인증이 필요해 자동 로그인을 건너뜁니다.":
        "  Two-factor authentication is required, so automatic login is skipped.",
    "  저장된 비밀번호가 더 이상 맞지 않습니다. 다시 입력이 필요합니다.":
        "  The saved password no longer works. You will need to enter it again.",
    "  자동 로그인에 실패했습니다: {reason}": "  Automatic login failed: {reason}",
    "  브라우저 쿠키를 확인하지 못해 건너뜁니다: {reason}":
        "  Could not read browser cookies, skipping: {reason}",
    "  브라우저 쿠키 기능을 쓸 수 없습니다: {reason}":
        "  The browser-cookie feature is unavailable: {reason}",
    "  {browser} 에 남아 있는 로그인 쿠키를 사용합니다 (@{user})":
        "  Using the login cookie left in {browser} (@{user})",
    "  브라우저에서 쓸 수 있는 인스타 로그인 쿠키를 찾지 못했습니다.":
        "  No usable Instagram login cookie was found in any browser.",
    "{browser}: 관리자 권한 필요": "{browser}: administrator rights required",
    "{browser}: 인스타그램에 로그인돼 있지 않음": "{browser}: not logged in to Instagram",
    "{browser}: 쿠키로 로그인하지 못함": "{browser}: could not log in with the cookie",
    "{browser}: {reason}": "{browser}: {reason}",
    "    힌트: 이 방식을 쓰려면 '관리자 권한으로 실행' 해야 합니다.":
        "    Hint: this method needs 'Run as administrator'.",
    "          번거로우면 아래에서 한 번만 로그인하세요(세션이 저장됩니다).":
        "          If that is inconvenient, just log in once below (the session is saved).",
    "  2단계 인증이 필요합니다.": "  Two-factor authentication is required.",
    "  세션을 저장했습니다. 다음부터는 로그인 없이 실행됩니다.":
        "  Session saved. From now on it will run without logging in.",
    "  세션 저장에 실패했습니다(이번 실행은 계속 진행): {reason}":
        "  Failed to save the session (this run continues anyway): {reason}",
    "로그인을 취소했습니다.": "Login was cancelled.",
    "ID 와 비밀번호를 모두 입력해야 합니다.": "You must enter both the ID and the password.",
    "2단계 인증을 취소했습니다.": "Two-factor authentication was cancelled.",
    "2단계 인증에 실패했습니다: {reason}": "Two-factor authentication failed: {reason}",
    "ID 또는 비밀번호가 틀렸습니다: {reason}": "Wrong ID or password: {reason}",
    "인스타그램이 본인 확인을 요구합니다. 브라우저나 휴대폰 앱에서 인스타그램에 "
    "로그인해 확인 절차를 마친 뒤 다시 시도해 주세요.\n  ({reason})":
        "Instagram is asking to verify it is you. Log in to Instagram in a browser or the "
        "phone app, finish the check, then try again.\n  ({reason})",
    "로그인에 실패했습니다: {reason}": "Login failed: {reason}",
    "\n브라우저 쿠키를 쓰지 못해 직접 로그인이 필요합니다.":
        "\nBrowser cookies could not be used, so you need to log in directly.",
    "(한 번만 하면 세션이 저장되어 다음 실행부터는 묻지 않습니다)":
        "(Do it once and the session is saved, so you won't be asked again)",
    "인스타그램 ID: ": "Instagram ID: ",
    "비밀번호(화면에 보이지 않음): ": "Password (hidden): ",
    "2단계 인증 코드: ": "Two-factor code: ",

    # --- 스토리 수집 (fetch.py) --------------------------------------
    "@{account}: 존재하지 않는 계정입니다.": "@{account}: no such account.",
    "@{account}: 비공개 계정이고 팔로우하고 있지 않습니다.":
        "@{account}: private account that you do not follow.",
    "@{account}: 스토리를 가져오지 못했습니다 ({reason}).":
        "@{account}: could not fetch stories ({reason}).",
    "@{account}: 스토리 하나를 건너뜁니다 ({reason}).":
        "@{account}: skipping one story ({reason}).",
    "로그인 세션이 만료됐습니다. '로그인'을 눌러 주세요.":
        "The login session has expired. Please press 'Log in'.",
    "인스타그램이 본인 확인을 요구합니다. 브라우저나 휴대폰 앱에서 확인 절차를 마친 뒤 다시 시도해 주세요.":
        "Instagram is asking to verify it is you. Finish the check in a browser or the phone "
        "app, then try again.",

    # --- 저장 (download.py) ------------------------------------------
    "  저장: {name}": "  Saved: {name}",
    "  건너뜀(이미 있음): {name}": "  Skipped (already there): {name}",
    "  실패: {name} ({reason})": "  Failed: {name} ({reason})",

    # --- 오류 창 (launcher.py) ---------------------------------------
    "\n\n자세한 내용: {path}": "\n\nDetails: {path}",

    # --- 예약 수집 ---------------------------------------------------
    "예약": "Schedule",
    "예약 ({count})": "Schedule ({count})",
    "예약 수집": "Scheduled collection",
    "예약 사용": "Enable schedule",
    "주기": "Repeat",
    "매일": "Daily",
    "시간마다": "Every N hours",
    "시각": "Time",
    "시간": "hours",
    "대상 계정": "Accounts",

    # 예약 목록 / 반복 설정
    "예약 목록": "Schedules",
    "새 예약": "New",
    "실행": "Run",
    "이번만": "Once",
    "{time} 에 한 번": "Once at {time}",
    "마지막 실행:": "Last run:",
    "예약 수정": "Edit schedule",
    "수정": "Edit",
    "삭제": "Delete",
    "켜기/끄기": "On / off",
    "반복": "Repeat",
    "일마다": "Every N days",
    "사용자 지정": "Custom",
    "간격": "Every",
    "일": "days",
    "예) 1:30": "e.g. 1:30",
    "예) 9:30": "e.g. 9:30",
    "매일 {time}": "Daily at {time}",
    "{n}일마다 {time}": "Every {n} day(s) at {time}",
    "{n}시간마다": "Every {n} hour(s)",
    "{interval} 간격": "Every {interval}",
    "전체 계정": "All accounts",
    "꺼짐": "Off",
    "등록 안 됨": "Not registered",
    "다음 {when}": "next {when}",
    "마지막 {when}": "last {when}",
    "  (예약이 없습니다. '새 예약'을 눌러 만드세요.)":
        "  (No schedules yet — press 'New' to add one.)",
    "예약 삭제": "Delete schedule",
    "이 예약을 삭제할까요?\n\n{what}": "Delete this schedule?\n\n{what}",
    "수정할 예약을 고르세요.": "Choose a schedule to edit.",
    "삭제할 예약을 고르세요.": "Choose a schedule to delete.",
    "켜거나 끌 예약을 고르세요.": "Choose a schedule to turn on or off.",
    "시각은 0:00~23:59 사이여야 합니다.": "The time must be between 0:00 and 23:59.",
    "간격은 {low}~{high} 사이여야 합니다.": "The interval must be between {low} and {high}.",

    # 실행 상태 / 기록 지우기
    "실행 중인 작업이 없습니다.": "No collection is running.",
    "{where} 수집 실행 중 — {when} 시작, 계정 {done}/{total}, {items}개 보관":
        "{where} collection running — started {when}, accounts {done}/{total}, {items} stored",
    "마지막 실행: {end} {label}, {items}개 보관":
        "Last run: {end} {label}, {items} stored",
    "창": "Window",
    # "완료" 는 위(창 공통)에 "Done" 으로 이미 있다. 여기에 "finished" 로 또 두었더니
    # **뒤에 온 것이 이겨** 알림 창 제목까지 "finished" 가 되어 있었다. 다시 넣지 말 것.
    "중지됨": "stopped",
    "오류": "error",
    "중단됨": "interrupted",
    "기록 지우기": "Clear log",
    "실행 기록과 진행 상태를 지울까요?\n예약별 '마지막 실행' 표시도 사라집니다.":
        "Clear the run log and the progress state?\n"
        "Each schedule's 'last run' will disappear too.",
    "실행 기록을 지웠습니다.": "The run log has been cleared.",
    "수집이 실행 중입니다. 끝난 뒤에 지워 주세요.":
        "A collection is running. Please clear it after it finishes.",
    "실행 중인 수집을 중지할까요?": "Stop the running collection?",

    # 일시정지 / 중지
    "일시정지": "Pause",
    "계속": "Resume",
    "중지": "Stop",
    "일시정지됨": "Paused",
    "계속하는 중...": "Resuming...",
    "중지하는 중...": "Stopping...",
    "작업을 중지했습니다.": "The job was stopped.",
    "작업을 취소했습니다.": "The job was cancelled.",
    "중지 요청으로 나머지 계정을 건너뜁니다.": "Stopped — skipping the remaining accounts.",
    "중지 요청으로 나머지 저장을 건너뜁니다.": "Stopped — skipping the remaining downloads.",

    # 선택 창의 '더 가져오기'
    "더 가져오기": "Fetch more",
    "가져오는 중...": "Fetching...",
    "더 가져오지 못했습니다.": "Could not fetch more.",
    "계정 선택": "Choose accounts",
    "다시 확인할 계정을 고르세요.": "Choose the accounts to check again.",
    "가져올 계정을 입력하세요.": "Type the accounts to fetch.",
    "직접 입력": "Type accounts",
    "가져올 계정": "Accounts to fetch",
    "가져오기": "Fetch",
    "가져올 계정을 고르거나 입력하세요.": "Choose or type at least one account.",
    "새 스토리 {count}개를 추가했습니다.": "Added {count} new story(s).",
    "추가된 새 스토리가 없습니다.": "No new stories were added.",

    "비워 두면 등록된 계정 전체를 확인합니다.":
        "Leave empty to check every registered account.",
    "목록에서 가져오기": "Take from list",
    "즐겨찾기만 가져오기": "Favorites only",
    "보관 기간(일)": "Keep for (days)",
    "보관 중": "In storage",
    "저장하기": "Save",
    "비우기": "Clear",
    "최근 실행 기록": "Recent runs",
    "아직 실행 기록이 없습니다.": "No runs yet.",
    "저장": "Save",
    "닫기": "Close",
    "예약을 등록했습니다.": "The schedule has been registered.",
    "예약을 해제했습니다.": "The schedule has been removed.",
    "예약 등록에 실패했습니다: {reason}": "Could not register the schedule: {reason}",
    "보관함을 비웠습니다. ({count}개)": "Storage cleared. ({count} items)",
    "보관함 비우기": "Clear storage",
    "보관 중인 스토리 {count}개가 있습니다.": "There are {count} stored stories.",
    "어떻게 비울까요?": "How would you like to clear them?",
    "전체": "All",
    "직접 선택": "Choose",
    "보관함에서 {count}개를 지웠습니다.": "Deleted {count} item(s) from storage.",
    "지운 항목이 없습니다.": "Nothing was deleted.",
    "보관 중인 스토리 {count}개를 지울까요?": "Delete the {count} stored stories?",
    "보관 중인 스토리가 없습니다.": "There are no stored stories.",
    "보관분 {count}개를 저장 폴더로 옮깁니다.": "Moving {count} stored item(s) to the save folder.",
    "예약 수집으로 모아 둔 스토리 {count}개가 있습니다.":
        "{count} stories were collected by the schedule.",
    "소스로 실행 중이라 파이썬 경로로 등록됩니다. exe 로 빌드한 뒤 다시 등록하는 편이 안전합니다.":
        "Running from source, so the task points at this Python. Registering again after "
        "building the exe is safer.",
    "절전에서 깨워 실행합니다. 완전히 끈 상태에서는 동작하지 않습니다.":
        "It wakes the PC from sleep. It cannot run while the PC is fully shut down.",

    # 창 없이 도는 예약 실행 기록 (schedule.log)
    "예약 수집 시작": "Scheduled collection started",
    "설정을 읽지 못해 건너뜁니다.": "Could not read settings, skipping.",
    "예약 대상 계정이 없어 건너뜁니다.": "No accounts to check, skipping.",
    "보관함에 {count}개를 넣었습니다.": "Stored {count} item(s).",
    "오래된 보관분 {count}개를 지웠습니다.": "Deleted {count} expired item(s).",
    "로그인하지 못했습니다: {reason}": "Could not log in: {reason}",
    "등록되지 않은 예약이라 작업을 해제합니다.":
        "This schedule no longer exists — removing its task.",
    "다른 수집이 이미 실행 중이라 이번 실행을 건너뜁니다.":
        "Another collection is already running, skipping this one.",
    "취소 요청으로 중지했습니다.": "Stopped on request.",
    "다음 계정 확인 전에 멈춥니다.": "Will stop before checking the next account.",

    # --- 여기부터 웹 전용 (exe 는 쓰지 않는다) --------------------------
    # 수집 소스와 자동 전환
    "자동 (fastdl → igram)": "Automatic (fastdl → igram)",
    # 사이트별 전환·실패 문구는 일부러 없앴다. 사용자가 사이트를 고르지 않으므로
    # 어디가 언제 막혔는지는 알려 주지 않고, 다 실패했을 때 아래 한 줄만 남긴다.
    # 수집 사이트를 다 해 보고도 안 되면 이 한 줄만 남긴다 (사이트별 사유는 안 남긴다).
    "서버에 연결하지 못했습니다.": "Could not connect to the server.",
    "@{account}: 비공개 계정이라 로그인 없이 가져올 수 없습니다.":
        "@{account}: private account — cannot be fetched without logging in.",
    "자동 접속이 막혀 있습니다": "automated access is blocked",
    "자동": "Automatic",
    "응답을 읽지 못했습니다.": "Could not read the response.",
    # 아래 넷은 화면에 바로 뜨지 않는다 — 소스를 접는 사유로만 쓰이고(조용히 전환),
    # 다 실패했을 때 나가는 문구는 "서버에 연결하지 못했습니다." 하나뿐이다.
    "로그인된 세션이 없습니다.": "No saved login session.",
    "인스타그램이 요청을 잠시 막았습니다.": "Instagram has temporarily blocked requests.",
    "인스타그램이 본인 확인을 요구합니다.": "Instagram is asking for a verification check.",
    "로그인 세션이 만료됐습니다.": "The login session has expired.",
    "이 사이트는 서명된 요청만 받습니다. 아직 지원하지 않습니다.":
        "This site only accepts signed requests, which are not supported yet.",

    # 이름 형식
    "이름 형식이 비어 있습니다.": "The name format is empty.",
    "모르는 토큰입니다: {token}": "Unknown token: {token}",
    "토큰 이름이 비어 있거나 잘못됐습니다.": "That token name is empty or invalid.",
    "파일명에 쓸 수 없는 글자가 있습니다: {chars}":
        "These characters cannot be used in a file name: {chars}",
    "번호 토큰은 하나만 쓸 수 있습니다.": "Only one number token is allowed.",
    "번호 토큰이 없어 같은 이름이 여러 개 나올 수 있습니다. 그럴 때는 뒤에 번호가 자동으로 붙습니다.":
        "Without a number token several files can end up with the same name. "
        "A number is appended automatically when that happens.",
    "[ ] 안에는 번호 토큰이 있어야 합니다.": "[ ] must contain a number token.",
    "'{' 를 닫는 '}' 가 없습니다.": "A '{' is never closed by a '}'.",
    "짝이 없는 '}' 가 있습니다.": "There is an unmatched '}'.",
    "'[' 를 닫는 ']' 가 없습니다.": "A '[' is never closed by a ']'.",
    "짝이 없는 ']' 가 있습니다.": "There is an unmatched ']'.",
    "'[' 안에 '[' 를 또 쓸 수 없습니다.": "A '[' cannot appear inside another '['.",
    "이름이 너무 깁니다 ({limit}자 이내).": "That name is too long (max {limit} characters).",
    "윈도우가 예약해 둔 이름입니다: {name}": "Windows reserves that name: {name}",
    "이름 앞뒤의 공백이나 끝의 마침표는 쓸 수 없습니다.":
        "A name cannot start or end with a space, or end with a period.",

    # 토큰 칩 묶음 이름과 설명 (filename.TOKENS 와 짝이다).
    # 짧은 낱말('시간', '일', '계정')을 쓰면 exe 의 예약 창 문구를 덮어쓴다.
    # filename.py 의 TOKENS 위 주석 참고.
    "날짜": "Date",
    "시각": "Time",
    "계정 이름": "Account",
    "번호": "Number",
    "기타": "Other",
    "원본 이름": "Original name",
    "YYMMDD": "YYMMDD",
    "년 (네 자리)": "Year (4 digits)",
    "년 (두 자리)": "Year (2 digits)",
    "월 (두 자리)": "Month (2 digits)",
    "일 (두 자리)": "Day (2 digits)",
    "HHMM": "HHMM",
    "시 (24시간)": "Hour (24h)",
    "분 (두 자리)": "Minute (2 digits)",
    "초 (두 자리)": "Second (2 digits)",
    "계정 아이디": "Account id",
    "@계정 아이디": "Account id with @",
    "번호 (하나뿐이면 생략)": "Number (omitted when there is only one)",
    "번호 (항상)": "Number (always)",
    "번호 (항상, 두 자리)": "Number (always, 2 digits)",
    "영상 또는 사진": "video or photo",

    # 웹 서버가 돌려주는 안내
    "확인할 계정이 없습니다. 계정을 먼저 추가해 주세요.":
        "No accounts to check. Add an account first.",
    "이미 가져오는 중입니다.": "Already fetching.",
    "이미 저장하는 중입니다.": "Already saving.",
    "그 작업을 찾을 수 없습니다.": "That job could not be found.",
    "그 미리보기를 찾을 수 없습니다.": "That preview could not be found.",
    "미리보기를 가져오지 못했습니다.": "Could not load that preview.",
    "저장 폴더를 먼저 정해 주세요.": "Choose a save folder first.",
    "고른 스토리가 없습니다.": "No stories selected.",
    "저장 폴더를 적어 주세요.": "Enter a save folder.",
    "전체 경로를 적어 주세요 (예: D:\\스토리).":
        "Enter a full path (for example D:\\Stories).",
    "data 폴더는 저장 폴더로 쓸 수 없습니다.":
        "The data folder cannot be used as the save folder.",
    "저장 폴더가 없습니다.": "The save folder does not exist.",
    "경로를 읽을 수 없습니다.": "That path cannot be read.",
    "그 폴더에 쓸 수 없습니다 ({reason}).": "Cannot write to that folder ({reason}).",
    "폴더를 열지 못했습니다 ({reason}).": "Could not open the folder ({reason}).",
    "추가할 계정을 적어 주세요.": "Enter the accounts to add.",
    "지울 계정을 골라 주세요.": "Choose the accounts to remove.",

    # 화면(브라우저)에서만 쓰는 문구
    "인스타그램 스토리 저장": "Instagram story saver",
    "계정 이름이나 링크 입력": "Input account name or link",
    "공백으로 구분해 여러 개 입력 가능": "Space-separated for several at once",
    "Enter: 목록에 추가 / Ctrl+Enter: 추가하고 바로 가져오기":
        "Enter: add to the list / Ctrl+Enter: add and fetch right away",
    "넓게 입력": "Expand",
    "계정 입력": "Enter accounts",
    # "확인" 은 exe 가 이미 "Confirm" 으로 갖고 있다 (gui.py 의 대화상자 버튼). 그대로 쓴다.
    "끌어서 너비 조절 (두 번 누르면 기본값)":
        "Drag to resize (double-click to reset)",
    "계정 목록 접기/펼치기": "Hide / show the account list",
    "{count}개 삭제": "Delete {count}",
    "{count}개를 목록에서 지울까요?": "Remove {count} accounts from the list?",
    "{count}개를 지웠습니다.": "Removed {count}.",
    "등록된 계정이 없습니다.": "No accounts registered yet.",
    "밝기 바꾸기": "Switch light / dark",
    "설정": "Settings",
    "삭제": "Delete",
    # 화면 위쪽 안내 띠는 없앴다. 추정 시각은 칸마다 '~' 와 아래 툴팁으로만 알린다.
    "원본 시각을 알 수 없어 추정한 시각입니다.": "Estimated — the original time is unknown.",
    "'스토리 가져오기'를 누르면 여기에 나옵니다.":
        "Press 'Fetch stories' and they will show up here.",
    "미리보기 실패": "(preview failed)",
    "{count}개": "{count}",
    "{count}개 선택": "{count} selected",
    # 첫 그리기 전에 잠깐 보이는 값. renderCount 가 곧 덮어쓴다.
    "0개 선택": "0 selected",
    "저장 폴더를 정해 주세요": "Choose a save folder",
    # "폴더 선택" 은 exe 가 이미 "Choose folder" 로 갖고 있다. 그대로 쓴다.
    "폴더 열기": "Open folder",
    "폴더 선택 창을 띄웠습니다. 다른 창 뒤에 있을 수 있습니다.":
        "Opened the folder chooser — it may be behind another window.",
    "여기서는 폴더 창을 띄울 수 없습니다. 경로를 직접 적어 주세요.":
        "The folder chooser cannot open here — type the path instead.",
    "폴더 창이 너무 오래 열려 있어 그만두었습니다.":
        "The folder chooser stayed open too long, so it was given up on.",
    "폴더 창을 띄우지 못했습니다 ({reason}).":
        "Could not open the folder chooser ({reason}).",
    "이름 형식": "Name format",
    "사용자 지정": "Custom",
    "해제 시 기본값으로 원본 이름을 씁니다.":
        "When off, the original name is used by default.",
    "기본값으로 되돌리기": "Reset to default",
    "그 폴더를 쓸 수 없습니다.": "That folder cannot be used.",
    "저장 폴더를 바꿨습니다.": "Save folder changed.",
    "계정을 먼저 추가해 주세요.": "Add an account first.",
    "@{name} 을(를) 목록에서 지울까요?": "Remove @{name} from the list?",
    "@{account} 확인 중 ({done}/{total})": "Checking @{account} ({done}/{total})",
    "{done}/{total} 계정": "{done}/{total} accounts",
    "{done}/{total} 저장 중": "Saving {done}/{total}",
    "가져오다 문제가 생겼습니다: {reason}": "Something went wrong while fetching: {reason}",
    "저장하다 문제가 생겼습니다: {reason}": "Something went wrong while saving: {reason}",
    "중지했습니다.": "Stopped.",
    "{ok}개 저장, {existed}개 건너뜀, {failed}개 실패":
        "{ok} saved, {existed} skipped, {failed} failed",
    "{name}: {reason}": "{name}: {reason}",
    "이미 있습니다: {names}": "Already there: {names}",
}

_lang = "ko"


def set_lang(name: str) -> None:
    global _lang
    _lang = name if name in LANGUAGES else "ko"


def lang() -> str:
    return _lang


def is_english() -> bool:
    return _lang == "en"


def t(text: str, **kw) -> str:
    """문장을 지금 언어로. 영어 표에 없으면 한국어 원문을 그대로 쓴다."""
    result = EN.get(text, text) if _lang == "en" else text
    return result.format(**kw) if kw else result
