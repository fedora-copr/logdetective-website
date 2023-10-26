from typing import Optional

from pydantic import AnyUrl, BaseModel

from backend.constants import BuildIdTitleEnum


class LogSchema(BaseModel):
    name: str
    content: str


class ContributeResponseSchema(BaseModel):
    """
    Data requested by frontend at the very beginning of review process. Those are
     fetched data (logs, spec, ...) and are needed for user to give a feedback why
     build failed.
    """
    build_id: Optional[int]
    build_id_title: BuildIdTitleEnum
    build_url: AnyUrl
    logs: list[LogSchema]
    spec_file: str


class SnippetSchema(BaseModel):
    """
    Snippet for log, each log may have 0 - many snippets.
    """
    # LINE_FROM:CHAR_FROM-LINE_TO:CHAR_TO
    # log_part: constr(regex=r"^\d+:\d+-\d+:\d+$")
    start_index: int
    end_index: int
    user_comment: str

    # def _splitter(self, return_lines: bool) -> tuple[int, int]:
    #     fst, snd = self.log_part.split("-")
    #     index_to_return = 0 if return_lines else 1
    #     return int(fst.split(":")[index_to_return]), int(
    #         snd.split(":")[index_to_return]
    #     )

    # def line_from_line_to(self) -> tuple[int, int]:
    #     return self._splitter(True)

    # def char_from_char_to(self) -> tuple[int, int]:
    #     return self._splitter(False)


class FeedbackLogSchema(LogSchema):
    """
    Feedback from user per individual log with user's comment.
    """
    snippets: list[SnippetSchema]


class FeedbackInputSchema(BaseModel):
    """
    Contains data from users with reasons why build failed. It is sent from FE
     and contains only inputs from user + spec and logs content.
    """
    username: Optional[str]
    logs: list[FeedbackLogSchema]
    fail_reason: str
    how_to_fix: str
    spec_file: str


class SpecfileSchema(BaseModel):
    # TODO: do we want to store spec_file separately
    #  in file or store content in one file?
    #  or the path means just its name?
    # path: Path
    content: str


class FeedbackSchema(BaseModel):
    """
    This schema is the final structure as we decided to store our data in json file
     from users feedbacks.
    """
    username: Optional[str]
    spec_file: SpecfileSchema
    logs: dict[str, FeedbackLogSchema]
    fail_reason: str
    how_to_fix: str


def schema_inp_to_out(inp: FeedbackInputSchema) -> FeedbackSchema:
    parsed_log_schema = {}
    for log_schema in inp.logs:
        parsed_log_schema[log_schema.name] = log_schema

    return FeedbackSchema(
        username=inp.username,
        spec_file={"content": inp.spec_file},
        logs=parsed_log_schema,
        fail_reason=inp.fail_reason,
        how_to_fix=inp.how_to_fix,
    )


def schema_out_to_fe(out: FeedbackSchema) -> FeedbackSchema:
    logs = {}
    for log_name, result_log_schema in out.logs.items():
        snippets = []
        for snippet in result_log_schema.snippets:
            snippets.append(snippet.dict())

        logs[log_name] = {"log": result_log_schema.content, "snippets": snippets}

    return FeedbackSchema(
        username=out.username,
        spec_file=out.spec_file,
        fail_reason=out.fail_reason,
        how_to_fix=out.how_to_fix,
        logs=logs,
    )
