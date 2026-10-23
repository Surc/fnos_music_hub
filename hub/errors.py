class HubError(Exception):
    """Public errors never contain upstream payloads, tokens or filesystem paths."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
