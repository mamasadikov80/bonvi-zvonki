"""Ilova darajasidagi xatoliklar.

Domen/application qatlami FastAPI'ni bilmaydi — shuning uchun bu yerda
oddiy Python xatoliklari, `main.py` esa ularni HTTP javoblarga aylantiradi.
"""


class AppError(Exception):
    """Barcha ilova xatoliklari uchun asos."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
