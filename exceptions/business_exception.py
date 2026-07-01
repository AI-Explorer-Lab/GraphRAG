from __future__ import annotations


class BusinessException(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ValidationException(BusinessException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=422)


class NotFoundException(BusinessException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=404)


class ServiceUnavailableException(BusinessException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=503)
