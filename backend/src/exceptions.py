from http import HTTPStatus

from fastapi import HTTPException


class NoDataFound(Exception):
    pass


class FetchError(HTTPException):
    """
    Unable to fetch the logs from the outside world for any reason.
    """

    def __init__(self, detail=None) -> None:
        super().__init__(status_code=HTTPStatus.NOT_FOUND, detail=detail)
