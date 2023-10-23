from http import HTTPStatus


class NoDataFound(Exception):
    pass


class HTTPException(Exception):
    """
    Wrapper to ged rid of detail field in Starlette's HTTPException
    """

    def __init__(self, status_code, msg=None) -> None:
        self.status_code = status_code
        self.msg = msg

    def __str__(self) -> str:
        return self.msg


class FetchError(HTTPException):
    """
    Unable to fetch the logs from the outside world for any reason.
    """

    def __init__(self, msg=None) -> None:
        super().__init__(status_code=HTTPStatus.NOT_FOUND, msg=msg)
