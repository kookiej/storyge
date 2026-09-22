"""Storyge_demo.exe 진입점 — 처음 만든 기본 화면.

PyInstaller 는 모듈(-m) 이 아니라 스크립트 파일을 필요로 하므로 이 파일을 둔다.
파이썬으로 직접 실행해도 똑같다:  .venv\\Scripts\\python.exe run.py
"""

import sys

from storyge.launcher import launch

if __name__ == "__main__":
    sys.exit(launch("classic"))
