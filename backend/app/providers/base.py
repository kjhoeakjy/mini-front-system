from __future__ import annotations


class ProviderError(Exception):
    """외부 자료 수집 실패. 메시지는 화면에 그대로 표시한다."""
