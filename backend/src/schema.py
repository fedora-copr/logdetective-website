from typing import Optional

from pydantic import AnyUrl, BaseModel, root_validator

from src.constants import BuildIdTitleEnum


def _check_spec_container_are_exclusively_mutual(_, values):
    spec_file = values.get("spec_file")
    container_file = values.get("container_file")
    if spec_file and container_file:
        raise ValueError("You can't specify both spec file and container file")

    return values


class NameContentSchema(BaseModel):
    # TODO: do we want to store spec_file and container_file separately
    #  in file or store content in one file? Or the path means just its name?
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
    logs: list[NameContentSchema]
    spec_file: Optional[NameContentSchema] = None
    container_file: Optional[NameContentSchema] = None

    # validators
    _normalize_spec_and_container_file = root_validator(pre=True, allow_reuse=True)(
        _check_spec_container_are_exclusively_mutual
    )


class SnippetSchema(BaseModel):
    """
    Snippet for log, each log may have 0 - many snippets.
    """

    # LINE_FROM:CHAR_FROM-LINE_TO:CHAR_TO
    # log_part: constr(regex=r"^\d+:\d+-\d+:\d+$")
    start_index: int
    end_index: int
    user_comment: str
    text: Optional[str] = None

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


class FeedbackLogSchema(NameContentSchema):
    """
    Feedback from user per individual log with user's comment.
    """

    snippets: list[SnippetSchema]


class _WithoutLogsSchema(BaseModel):
    username: Optional[str]
    fail_reason: str
    how_to_fix: str
    spec_file: Optional[NameContentSchema] = None
    container_file: Optional[NameContentSchema] = None

    # validators
    _normalize_spec_and_container_file = root_validator(pre=True, allow_reuse=True)(
        _check_spec_container_are_exclusively_mutual
    )


class FeedbackInputSchema(_WithoutLogsSchema):
    """
    Contains data from users with reasons why build failed. It is sent from FE
     and contains only inputs from user + spec and logs content.
    """

    logs: list[FeedbackLogSchema]


class FeedbackSchema(_WithoutLogsSchema):
    """
    This schema is the final structure as we decided to store our data in json file
     from users feedbacks.
    """

    logs: dict[str, FeedbackLogSchema]


def schema_inp_to_out(
    inp: FeedbackInputSchema, is_with_spec: bool = True
) -> FeedbackSchema:
    parsed_log_schema = {}
    for log_schema in inp.logs:
        parsed_log_schema[log_schema.name] = log_schema

    if is_with_spec:
        spec_or_container = {"spec_file": inp.spec_file}
    else:
        spec_or_container = {"container_file": inp.container_file}

    return FeedbackSchema(
        username=inp.username,
        logs=parsed_log_schema,
        fail_reason=inp.fail_reason,
        how_to_fix=inp.how_to_fix,
        **spec_or_container,
    )
