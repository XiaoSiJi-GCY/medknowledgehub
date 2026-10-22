class HubError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


class DependencyUnavailable(HubError):
    def __init__(self, service: str):
        super().__init__(f"{service} 暂不可用，请检查服务状态与配置。", 503, "dependency_unavailable")
