from http import HTTPStatus

from fastapi import HTTPException
from src.constants import LOG_DETECTIVE_MAX_ARTIFACT_SIZE


class FetchError(HTTPException):
    """
    Unable to fetch the logs from the outside world for any reason.
    """

    def __init__(self, detail=None) -> None:
        super().__init__(status_code=HTTPStatus.NOT_FOUND, detail=detail)


class NoDataFound(FetchError):
    pass


class MaximumArtifactSizeExceeded(HTTPException):
    """Artifacts exceeding maximum size can not be uploaded"""

    def __init__(self) -> None:
        super().__init__(
            status_code=HTTPStatus.CONTENT_TOO_LARGE,  # pylint: disable=E1101
            detail=f"Artifact exceeded maximum allowed size {LOG_DETECTIVE_MAX_ARTIFACT_SIZE} KB",
        )
