from typing import Optional

from pydantic import AnyUrl, BaseModel, constr

from backend.constants import BuildIdTitleEnum

# TODO: there's a lot of small changes between the same schemas basically
#  unify those unicorn schemas once we fully agree on backend <-> frontend data


class ContributeResponseSchema(BaseModel):
    build_id: Optional[int]
    build_id_title: BuildIdTitleEnum
    build_url: AnyUrl
    logs: list[dict[str, str]]
    spec_file: str


class SpecfileSchema(BaseModel):
    # TODO: do we want to store specfile separately
    #  in file or store content in one file?
    #  or the path means just its name?
    # path: Path
    content: list[str]


class SnippetSchema(BaseModel):
    start_index: int
    end_index: int
    user_comment: str


class LogSchema(BaseModel):
    name: str
    log: str
    snippets: list[SnippetSchema]


class ResultInputSchema(BaseModel):
    username: Optional[str]
    logs: list[LogSchema]
    fail_reason: str
    how_to_fix: str
    specfile: Optional[str] = None


class SnippetResultSchema(BaseModel):
    log_part: constr(regex=r"^\d+:\d+-\d+:\d+$")
    # LINE_FROM:CHAR_FROM-LINE_TO:CHAR_TO
    user_comment: str

    def _splitter(self, return_lines: bool) -> tuple[int, int]:
        fst, snd = self.log_part.split("-")
        index_to_return = 0 if return_lines else 1
        return int(fst.split(":")[index_to_return]), int(
            snd.split(":")[index_to_return]
        )

    def line_from_line_to(self) -> tuple[int, int]:
        return self._splitter(True)

    def char_from_char_to(self) -> tuple[int, int]:
        return self._splitter(False)


class ResultLogSchema(BaseModel):
    log: list[str]
    snippets: list[SnippetResultSchema]


class ResultSchema(BaseModel):
    username: Optional[str]
    reviewers: list[str]
    specfile: SpecfileSchema
    logs: dict[str, ResultLogSchema]
    fail_reason: str
    how_to_fix: str


class SnippetReviewSchema(SnippetResultSchema):
    start_index: int
    end_index: int


class ResultReviewLogSchema(BaseModel):
    log: list[str]
    snippets: list[SnippetReviewSchema]


class ResultReviewSchema(BaseModel):
    username: Optional[str]
    reviewers: list[str]
    specfile: SpecfileSchema
    logs: dict[str, ResultReviewLogSchema]
    fail_reason: str
    how_to_fix: str


def _find_line_for_index(log_lines: list[str], index: int) -> Optional[int]:
    curr_index = 0
    line_index = None
    for line in log_lines:
        if index < curr_index + len(line):
            line_index = log_lines.index(line) + 1
            break

        curr_index += len(line) + 1

    return line_index


def _get_result_log_schema(log_schema: LogSchema) -> ResultLogSchema:
    log_lines = log_schema.log.split("\n")
    result = {"log": log_schema.log.split("\n")}
    snippets_parsed = []
    for snippet in log_schema.snippets:
        line_from = _find_line_for_index(log_lines, snippet.start_index)
        line_to = _find_line_for_index(log_lines, snippet.end_index)
        log_part = f"{line_from}:{snippet.start_index}-{line_to}:{snippet.end_index}"
        snippets_parsed.append(
            {
                "user_comment": snippet.user_comment,
                "log_part": log_part,
                "start_indnex": snippet.start_index,
                "end_indnex": snippet.end_index,
            }
        )

    result["snippets"] = snippets_parsed
    return ResultLogSchema(**result)


def schema_inp_to_out(inp: ResultInputSchema, spec_content: str) -> ResultSchema:
    parsed_log_schema = {}
    for log_schema in inp.logs:
        parsed_log_schema[log_schema.name] = _get_result_log_schema(log_schema)

    return ResultSchema(
        username=inp.username,
        reviewers=[],
        specfile={"content": spec_content.split("\n")},
        logs=parsed_log_schema,
        fail_reason=inp.fail_reason,
        how_to_fix=inp.how_to_fix,
    )


def schema_out_to_fe(out: ResultSchema) -> ResultReviewSchema:
    logs = {}
    for log_name, result_log_schema in out.logs.items():
        snippets = []
        for snippet in result_log_schema.snippets:
            char_from, char_to = snippet.char_from_char_to()
            the_rest_of_dict = {
                "start_index": char_from,
                "end_index": char_to,
            }
            snippets.append(snippet.dict() | the_rest_of_dict)

        logs[log_name] = {"log": result_log_schema.log, "snippets": snippets}

    return ResultReviewSchema(
        username=out.username,
        reviewers=out.reviewers,
        specfile=out.specfile,
        fail_reason=out.fail_reason,
        how_to_fix=out.how_to_fix,
        logs=logs,
    )
