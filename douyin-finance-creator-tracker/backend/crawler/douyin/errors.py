class DouyinCollectorError(RuntimeError):
    """Base error for an actionable collection failure."""


class LoginExpired(DouyinCollectorError):
    """The persistent Chrome profile is not authenticated with Douyin."""


class RateLimited(DouyinCollectorError):
    """Douyin temporarily refused requests from the browser session."""


class DataFetchError(DouyinCollectorError):
    """The page did not expose the expected public data."""
