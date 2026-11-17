class ServiceError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 오류 메시지를 담는 예외."""


class PermissionDenied(ServiceError):
    """권한 없는 동작을 시도했을 때."""

    def __init__(self, message: str = "권한이 없습니다."):
        super().__init__(message)
