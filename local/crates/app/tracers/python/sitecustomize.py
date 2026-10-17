# 싱크독 실행 기록: `syncdoc-local trace` 가 PYTHONPATH 에 이 폴더를 넣으면 파이썬이 시작할 때 자동으로 읽힌다.
# SYNCDOC_TRACE_OUT 이 없으면 아무것도 하지 않는다.
import os

if os.environ.get("SYNCDOC_TRACE_OUT"):
    try:
        import syncdoc_tracer

        syncdoc_tracer.install()
    except Exception as error:  # 기록 때문에 앱이 못 뜨는 일은 없게
        import sys

        print(f"[syncdoc] 실행 기록을 켜지 못했습니다: {error}", file=sys.stderr)
