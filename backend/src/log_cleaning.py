"""
Some utility functions for preparing/cleaning json files before sanitization.
"""

import html
import logging

import regex as re

from src.schema import SnippetSchema, FeedbackLogSchema
from src.constants import LOGGER_NAME
from src.sanitization import SchemaRedactionPipelineStep


LOGGER = logging.getLogger(LOGGER_NAME)


# expand search area for snippets by (DEFAULT_RATIO * 100) % of the log's length
DEFAULT_RATIO = 0.02

# we ignore snippets that would be 5 and less characters long,
# as they probably don't contain any useful information
# NOTE: maybe we should also set it to 10, as is the case
# with fail_reason, how_to_fix and user_comments...
SNIPPET_LENGTH_THRESHOLD = 5

# defines the area (in characters) around the snippet for which we try to find newlines
# and adjust the snippets such that they contain the whole lines from the log,
# since the indexes are often off-by-one and inferred snippet texts might look weird,
# e.g. "\nE[rror: Something happene]d\n" instead of "\n[Error: Something happened]\n"
DEFAULT_MARGIN_FOR_NEWLINE_SNAP = 5


def html_careful_unescape(text: str) -> str:
    """More careful version of html.unescape(), requires sequence to end in semicolon"""
    # This regex ONLY matches sequences ending in a semicolon
    # Matches: &lt; &gt; &copy; &#169; &#xa9; ...
    # Non-match: &section
    pattern = r"&([a-zA-Z0-9]+;|#[0-9]+;|#x[a-fA-F0-9]+;)"

    def replace_match(match: re.Match) -> str:
        return html.unescape(match.group(0))

    return re.sub(pattern, replace_match, text)


def snap_snippet_to_newline(log_content: str, snippet: SnippetSchema, margin: int):
    """
    Try to snap the text to a full line, if \n is present around
    the margins of the snippet for a clean "full-line" snippet text.
    """
    # find the position right after `\\n` in the area around start index (if possible)
    lookback_start = max(0, snippet.start_index - margin)
    # we also include first two characters of the snippet, since they often can be '\n'
    lookback_area = log_content[lookback_start : snippet.start_index + 2]
    newline_pos = lookback_area.rfind("\n")
    new_start = (
        lookback_start + newline_pos + 1 if newline_pos != -1 else snippet.start_index
    )
    # find the position of \n right after end_index (if possible)
    lookforward_end = min(len(log_content), snippet.end_index + margin)
    lookforward_area = log_content[snippet.end_index : lookforward_end]
    nl_forward = lookforward_area.find("\n")
    new_end = snippet.end_index + nl_forward if nl_forward != -1 else snippet.end_index

    snippet.start_index = new_start
    snippet.end_index = new_end
    snippet.text = log_content[new_start:new_end]


def log_print(text: str) -> str:
    """Snippet print for debugging"""
    snippet = f"{text[0:50]} ... {text[-50:]}" if len(text) > 150 else text
    return snippet.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def regex_based_snapping(
    log: str, snippet: SnippetSchema, index: int, file: str
) -> bool:
    """
    Search for the snippet text in the log using regexes.
    If no matches are found in the small search-window (careful approach),
    the indexes are really broken and we resort to this regex approach.
    """

    def distance(match: re.Match) -> int:
        return abs(
            match.start() - snippet.start_index
        )  # lambda m, s=start: abs(m.start() - s)

    if not snippet.text:
        return False
    matches: list[re.Match] = list(re.finditer(re.escape(snippet.text), log))
    if not matches:
        LOGGER.warning("%s[%d] snippet not found", file, index + 1)
        return False
    closest_match = min(matches, key=distance)
    snippet.start_index = closest_match.start()
    snippet.end_index = closest_match.end()
    return True


def careful_snapping(log: str, snippet: SnippetSchema, ratio: float) -> bool:
    """
    Adjust snippet indexes based on a local search area around the snippet.

    Example: snippet = consectetur
                                 | ------- |
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do ..."
               misaligned indexes > | -------- |
               we search here > |<<<|          |>>>|
    """

    def distance(pos: int) -> int:
        return abs(
            pos - snippet.start_index
        )  # lambda m, s=snippet.start_index: abs(m - s)

    start_point = max(snippet.start_index - int(ratio * len(log)), 0)
    end_point = min(snippet.end_index + int(ratio * len(log)), len(log))
    if not snippet.text:
        return False

    matches = []
    search_pos = start_point
    while True:
        idx = log.find(snippet.text, search_pos, end_point)
        if idx == -1:
            break
        matches.append(idx)
        search_pos = idx + 1  # skip over so we don't find the same match

    if matches:
        snippet.start_index = min(matches, key=distance)
        snippet.end_index = snippet.start_index + len(snippet.text)
        return True
    return False


def snap_indexes_to_text(
    log_schema: FeedbackLogSchema,
    ratio: float = DEFAULT_RATIO,
) -> None:
    """
    Synchronize the indexes corresponding to the snippet with its log content.

    We search for the snippet text in the log's small area around where the indexes point to.
    By default, this area is expanded on each side by `ratio` % of the full log length.
    If `absolute` is set to a positive number,
    the search area will be expanded by `absolute` chars on each side.

    Return the number of index-adjusted snippets.
    """

    for i, snippet in enumerate(log_schema.snippets):
        if not snippet.text:
            continue
        snap_worked = careful_snapping(log_schema.content, snippet, ratio)
        if snap_worked:
            snap_snippet_to_newline(
                log_schema.content, snippet, margin=DEFAULT_MARGIN_FOR_NEWLINE_SNAP
            )
            continue
        LOGGER.warning(
            "%s[%d]: snippet not found in %s area around <%d:%d>",
            log_schema.name,
            i + 1,
            f"{int(100 * ratio)} %",
            snippet.start_index,
            snippet.end_index,
        )
        regex_worked = regex_based_snapping(
            log_schema.content, snippet, i, log_schema.name
        )
        if regex_worked:
            snap_snippet_to_newline(
                log_schema.content, snippet, margin=DEFAULT_MARGIN_FOR_NEWLINE_SNAP
            )
            continue
        LOGGER.warning(
            "%s[%d]: snippet not found at all: %s",
            log_schema.name,
            i + 1,
            log_print(snippet.text),
        )


def log_schema_redaction(
    log: str,
    redaction: SchemaRedactionPipelineStep,
    snippet_list: list[SnippetSchema],
) -> str:
    """
    Redact personal information based on 'redaction' pattern and replacement,
    while also keeping start-end snippet indexes consistent with changes.
    """
    matches = list(redaction.pattern.finditer(log))

    # We go in reverse, because if we change something at the start, not only are all snippets
    # AFTER affected, but also the match indexes are now all wrong. We would have to have some
    # sort of an overall delta-correction variable, which we would need to factor into the match
    # start/end indexes. Going in reverse means only updating the snippets while not disrupting
    # match indexes, which is more elegant.
    for match in reversed(matches):
        start_pos, end_pos = match.span()
        # the replacement is a) a callback, and we want to obtain how it changed the match
        # or b) a placeholder string, so we just expand it (since it might have groups)
        replacement = (
            redaction.replacement(match)
            if callable(redaction.replacement)
            else match.expand(redaction.replacement)
        )
        delta = len(replacement) - (end_pos - start_pos)
        log = log[:start_pos] + replacement + log[end_pos:]
        for snippet in snippet_list:
            # if the snippets starts/ends "inside" the match, then we snap to the start/end of
            # redaction, if the snippets start/end "after" the match, we change them by delta
            if snippet.start_index >= end_pos:
                snippet.start_index += delta
            elif start_pos < snippet.start_index < end_pos:
                snippet.start_index = start_pos

            if snippet.end_index >= end_pos:
                snippet.end_index += delta
            elif start_pos < snippet.end_index < end_pos:
                snippet.end_index = start_pos + len(replacement)
    return log
