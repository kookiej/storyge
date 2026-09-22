# exe 두 개를 만든다.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# 결과물:
#   dist\Storyge.exe        인스타 디자인 (다크/라이트, 한국어/영어, 예약 수집)
#   dist\Storyge_demo.exe   처음 만든 기본 화면
#
# 둘 다 exe 옆의 data 폴더를 쓰므로 계정과 세션은 공유된다.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# instagrapi 는 Pillow>=12.2 를 요구하는데, 전역 파이썬에 설치된 moviepy 는 pillow<12 를
# 요구해 서로 공존할 수 없다. 그래서 이 프로젝트만의 .venv 에서 빌드한다.
# 전역 환경은 건드리지 않는다.
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "빌드용 .venv 를 만듭니다..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "필요한 패키지 확인 중..." -ForegroundColor Cyan
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r requirements.txt
& $py -m pip install -q pyinstaller

$targets = @(
    @{ Script = "run.py";       Name = "Storyge_demo"; Label = "기본 화면 (demo)" },
    @{ Script = "run_insta.py"; Name = "Storyge";      Label = "인스타 디자인" }
)

# 로고가 없으면 만든다 (assets\make_logo.py 가 유일한 원본이다).
# --icon 은 exe 파일 자체의 아이콘이고, --add-data 로 넣는 사본은 창이 띄울 때 쓴다
# (gui._set_icon 이 paths.LOGO_ICO 에서 읽는다 — onefile 은 sys._MEIPASS 에 풀린다).
$logo = "assets\logo.ico"
if (-not (Test-Path $logo)) {
    Write-Host "로고를 만듭니다..." -ForegroundColor Cyan
    & $py assets\make_logo.py
}

foreach ($t in $targets) {
    Write-Host "`n[$($t.Name)] $($t.Label) 빌드 중... (1~3분)" -ForegroundColor Cyan
    & $py -m PyInstaller $t.Script `
        --onefile `
        --windowed `
        --name $t.Name `
        --clean `
        --noconfirm `
        --icon $logo `
        --add-data "$logo;assets" `
        --collect-all browser_cookie3 `
        --collect-all instagrapi `
        --collect-submodules pydantic
}

Write-Host ""
$ok = $true
foreach ($t in $targets) {
    $exe = "dist\$($t.Name).exe"
    if (Test-Path $exe) {
        $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
        Write-Host "완료: $exe ($size MB) - $($t.Label)" -ForegroundColor Green
    } else {
        Write-Host "실패: $exe 를 만들지 못했습니다." -ForegroundColor Red
        $ok = $false
    }
}

if (-not $ok) { exit 1 }
Write-Host "`nexe 를 원하는 폴더에 두고 더블클릭하세요. 설정은 exe 옆 data 폴더에 저장됩니다."
