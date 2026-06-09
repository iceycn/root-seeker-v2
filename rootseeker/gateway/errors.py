from __future__ import annotations

__all__ = [
    "GatewayError",
    "GatewayMethodNotFoundError",
    "GatewayValidationError",
]


class GatewayError(RuntimeError):
    code = "gateway_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GatewayMethodNotFoundError(GatewayError):
    code = "method_not_found"


class GatewayValidationError(GatewayError):
    code = "validation_error"
