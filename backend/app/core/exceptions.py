class CueError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(CueError):
    def __init__(self, message: str = "Invalid or expired authentication credentials"):
        super().__init__("AUTH_ERROR", message, 401)


class PolicyBlockedError(CueError):
    def __init__(self, message: str = "Destructive or unauthorized action blocked by security policy"):
        super().__init__("POLICY_BLOCKED", message, 403)


class IdempotencyConflictError(CueError):
    def __init__(self, message: str = "Operation ID reused with mismatched payload"):
        super().__init__("IDEMPOTENCY_CONFLICT", message, 409)


class QuotaExceededError(CueError):
    def __init__(self, message: str = "Monthly voice transaction quota reached for current plan"):
        super().__init__("QUOTA_EXCEEDED", message, 402)


class AudioValidationError(CueError):
    def __init__(self, message: str = "Audio file failed validation or sounded unclear"):
        super().__init__("AUDIO_INVALID", message, 422)


class InsufficientStockError(CueError):
    def __init__(self, available: float, product_name: str):
        self.available = available
        self.product_name = product_name
        super().__init__(
            "INSUFFICIENT_STOCK",
            f"Negative stock blocked: {product_name} has only {available:g} in stock.",
            409,
        )


class MemoryBoundaryError(CueError):
    def __init__(self, days_ago: int):
        self.days_ago = days_ago
        super().__init__(
            "MEMORY_BOUNDARY_30D",
            "Conversational chat memory covers only the past 30 days (1 month). Please check Reports & Ledger for older records.",
            200,
        )
