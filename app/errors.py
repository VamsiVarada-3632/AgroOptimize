"""Errors shared across the app."""


class FeatureUnavailable(RuntimeError):
    """A feature is disabled because the OFFICIAL dataset it needs is missing. Raised instead of falling back to
    synthetic or estimated data; the API returns it as HTTP 501 with the missing dataset named."""

    def __init__(self, feature: str, missing_dataset: str, detail: str = ""):
        self.feature, self.missing_dataset = feature, missing_dataset
        super().__init__(f"{feature} is unavailable: official dataset missing - {missing_dataset}. {detail}".strip())
