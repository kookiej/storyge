"""Storyge.exe 진입점 — 인스타그램 앱의 디자인 언어를 참고한 화면.

밝기(다크/라이트)와 언어는 data/config.json 에 저장된 값을 따르고, 창 안에서 바꿀 수 있다.
Storyge_demo.exe 와 같은 data 폴더를 쓰므로 계정·세션은 공유된다.

인자로 --scheduled 를 주면 창 없이 예약 수집만 하고 끝낸다 (작업 스케줄러가 부른다).
예약이 여러 개일 수 있으므로 --task <식별자> 로 어느 예약인지 함께 넘어온다.
"""

import sys

from storyge.launcher import launch


def _task_id(args: list[str]):
    """--task 뒤의 값. 없으면 None (업데이트 전에 등록된 작업이 이렇게 부른다)."""
    if "--task" not in args:
        return None
    index = args.index("--task") + 1
    return args[index] if index < len(args) else None


if __name__ == "__main__":
    argv = sys.argv[1:]
    sys.exit(launch(scheduled="--scheduled" in argv, schedule_id=_task_id(argv)))
