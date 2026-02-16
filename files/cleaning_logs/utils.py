"""
Some utility functions for preparing/cleaning json files before sanitization.
"""

import os
import html
import logging
import glob
from typing import Iterator, Iterable, Any, Callable, Optional

import regex as re

from resources import (
    UNICODE_ESCAPE_BY_BYTE_UTF8,
    DEFAULT_MARGIN_FOR_NEWLINE_SNAP,
    SNIPPET_LENGTH_THRESHOLD,
    DEFAULT_RATIO,
    DEFAULT_ABSOLUTE,
)

from sanitization_regexes import FALSE_POSITIVES_PARENTHESISED_NAMES, NAME_PLACEHOLDER

logger = logging.getLogger(__name__)


def check_for_broken_escapes(string_from_json: str) -> bool:
    """
    Check for [\\u00c2-\\u00f4][\\u0080-\\u00bf]+ but literally as escape sequences.
    Return True if any such sequence is found.
    We do this on raw files, since json.load() would un-escape.
    """
    return bool(UNICODE_ESCAPE_BY_BYTE_UTF8.search(string_from_json))


def files_in_dirs(dir_list: Iterable[str], suffixes: tuple[str]) -> Iterator[str]:
    """
    Finds files matching suffixes across multiple directories recursively.
    """
    if not suffixes:
        return
    for directory in dir_list:
        pattern = os.path.join(directory, "**", "*")
        for path in glob.iglob(pattern, recursive=True):
            if os.path.isfile(path) and path.endswith(suffixes):
                yield os.path.normpath(path)


def on_all_strings_in_json(
    item: Any, apply_func: Callable, *args: Any, **kwargs: Any
) -> Any:
    """
    Recursively find strings in json and apply the a given function.
    The function should have a func(str, ...) -> str signature.
    """
    if isinstance(item, dict):
        return {
            k: on_all_strings_in_json(v, apply_func, *args, **kwargs)
            for k, v in item.items()
        }
    if isinstance(item, list):
        return [on_all_strings_in_json(i, apply_func, *args, **kwargs) for i in item]
    if isinstance(item, str):
        try:
            return apply_func(item, *args, **kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Couldn't correctly apply {apply_func} on some string"
            ) from exc
    return item  # fall-through case -> no function used


def convert_mojibake_to_utf8(string: str) -> str:
    """Try to apply the encoding fix"""
    try:
        fixed = string.encode("latin-1").decode("utf-8")
        return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        return string


def html_careful_unescape(text: str) -> str:
    """More careful version of html.unescape(), requires sequence to end in semicolon"""
    # This regex ONLY matches sequences ending in a semicolon
    # Matches: &lt; &gt; &copy; &#169; &#xa9; ...
    # Non-match: &section
    pattern = r"&([a-zA-Z0-9]+;|#[0-9]+;|#x[a-fA-F0-9]+;)"

    def replace_match(match: re.Match) -> str:
        return html.unescape(match.group(0))

    return re.sub(pattern, replace_match, text)


def adjust_start_index_to_newline(
    log_content: str, start_index: int, margin: int = 0
) -> int:
    """Find the position right after `\\n` in the area around start index (if possible)."""
    lookback_start = max(0, start_index - margin)
    # we also include first two characters of the snippet, since they often can be '\n'
    lookback_area = log_content[lookback_start : start_index + 2]
    newline_pos = lookback_area.rfind("\n")
    new_start_index = (
        lookback_start + newline_pos + 1 if newline_pos != -1 else start_index
    )
    return new_start_index


def adjust_end_index_to_newline(
    log_content: str, end_index: int, margin: int = 0
) -> int:
    """Find the position of `\\n` right after `end_index` (if possible)."""
    lookforward_end = min(len(log_content), end_index + margin)
    lookforward_area = log_content[end_index:lookforward_end]
    nl_forward = lookforward_area.find("\n")
    new_end_index = end_index + nl_forward if nl_forward != -1 else end_index
    return new_end_index


def snap_snippet_to_newline(log_content: str, snippet: dict, margin: int = 0):
    """
    Try to snap the text to a full line, if \n is present around
    the margins of the snippet for a clean "full-line" snippet text.
    """
    # defaults are provided for linters, we can safely assume the snippet has non-None values.
    start_index = int(snippet.get("start_index", 0))
    end_index = int(snippet.get("end_index", len(log_content)))

    new_start = adjust_start_index_to_newline(log_content, start_index, margin=margin)
    new_end = adjust_end_index_to_newline(log_content, end_index, margin=margin)
    snippet["start_index"] = new_start
    snippet["end_index"] = new_end

    text = log_content[new_start:new_end]
    snippet["text"] = text


def add_text_to_snippets(
    json_root_object: dict,
    margin_for_newline_snap: int = DEFAULT_MARGIN_FOR_NEWLINE_SNAP,
) -> dict[str, list[str]]:
    """
    Traverse the json_root_object and add text to snippets where missing.

    We try to follow the schema:
        for full text content of the log: `.logs.logname.content`
        for snippet content: `.logs.logname.snippets[i].text`
        for start/end indexes of snippets: `.logs.logname.snippets[i].[start|end]_index`

    Return how many snippet texts were successfully added to the log-file.
    """
    added_snippets: dict[str, list[str]] = {}
    log_dict = json_root_object.get("logs", None)
    if not isinstance(log_dict, dict):
        return {}
    for log_name, log_info in log_dict.items():
        if not (isinstance(log_name, str) and isinstance(log_info, dict)):
            continue
        log_content = log_info.get("content", None)
        snippet_list = log_info.get("snippets", [])
        if not (log_content and isinstance(snippet_list, list)):
            continue
        for i, snippet in enumerate(snippet_list):
            if not isinstance(snippet, dict):
                continue
            start_index: Optional[int] = snippet.get("start_index")
            end_index: Optional[int] = snippet.get("end_index")
            text: Optional[str] = snippet.get("text", None)
            if start_index is None or end_index is None:
                logger.error("%s[%d]: Missing some index", log_name, i + 1)
                continue
            if text:
                continue
            if start_index > end_index:  # start is AFTER the end, try swapping
                snippet["start_index"] = end_index
                snippet["end_index"] = start_index
            if any(
                [
                    # too short of a snippet to contain anything useful
                    end_index - start_index <= SNIPPET_LENGTH_THRESHOLD,
                    # this would mean the snippet is the entire log
                    start_index == 0 and end_index in [-1, len(log_content)],
                ]
            ):
                snippet["text"] = None
                continue
            if log_name not in added_snippets:
                added_snippets[log_name] = []

            snap_snippet_to_newline(
                log_content, snippet, margin=margin_for_newline_snap
            )

            text = str(snippet.get("text", ""))

            logger.info(
                "%s[%d] <%d:%d> adding: %s",
                log_name,
                i + 1,
                start_index,
                end_index,
                log_print(text),
            )
            added_snippets[log_name].append(text)

    return added_snippets


def check_snippet_fields(snippet: dict, index: int, log_name: str, warn: bool) -> bool:
    """Return False if any critical field is missing from the snippet."""
    supposed_start = snippet.get("start_index", None)
    supposed_end = snippet.get("end_index", None)
    text = snippet.get("text", None)
    if supposed_start is None:
        if warn:
            logger.warning("%s[%d]: Missing start index", log_name, index + 1)
        return False
    if supposed_end is None:
        if warn:
            logger.warning("%s[%d]: Missing end index", log_name, index + 1)
        return False
    if not text:
        if warn:
            logger.warning("%s[%d]:Missing text", log_name, index + 1)
        return False
    return True


def check_all_snippets_in_file(json_obj: dict, file_name: str, warn=False) -> int:
    """
    Return how many snippets in the file are somehow broken, for example
    - the text does not match the log content,
    - or some critical field is missing
    """
    result = 0
    log_dict = json_obj.get("logs", None)
    # logger.info("Checking snippets in %s", file_name)
    if not isinstance(log_dict, dict):
        return result

    for log_name, log_info in log_dict.items():
        if not (isinstance(log_name, str) and isinstance(log_info, dict)):
            continue
        log_content = log_info.get("content", None)
        snippet_list = log_info.get("snippets", [])
        if not (isinstance(log_content, str) and isinstance(snippet_list, list)):
            continue
        for i, snippet in enumerate(snippet_list):
            if not check_one_snippet(log_content, i, snippet, log_name, warn):
                logger.warning("%s: %s[%d] does not match ", file_name, log_name, i + 1)
                result += 1
    return result


def log_print(text: str) -> str:
    """Snippet print for debugging"""
    snippet = f"{text[0:50]} ... {text[-50:]}" if len(text) > 150 else text
    return snippet.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def check_one_snippet(
    log: str, index: int, snippet: dict, log_name: str, warn: bool
) -> bool:
    """Compare snippets with their source"""
    if not check_snippet_fields(snippet, index, log_name, warn):
        return True  # something is missing -> we can't check
    start = int(snippet.get("start_index", 0))
    end = int(snippet.get("end_index", len(log)))
    text = str(snippet.get("text"))
    # In case the snippet indexes are somehow broken, we use null as a placeholder for "text"
    # Snippets such as these should be skipped in this check
    if not text:
        return True
    match = log[start:end] == text
    if not match:
        logger.info("IN LOG: %s", log_print(log[start:end]))
        logger.info("SNIPPT: %s", log_print(text))
    return match


def get_search_start(start: int, log: str, ratio: float, absolute: int) -> int:
    """Get start of the search-area for snippet index adjusting"""
    if absolute > 0:
        new_start = start - absolute
    else:
        new_start = start - int(ratio * len(log))
    return max(new_start, 0)


def get_search_end(end: int, log: str, ratio: float, absolute: int) -> int:
    """Get end of the search-area for snippet index adjusting"""
    if absolute > 0:
        new_end = end + absolute
    else:
        new_end = end + int(ratio * len(log))
    return min(new_end, len(log))


def find_snippet_matches_in_log(log: str, text: str, start: int, end: int) -> list[int]:
    """
    Find all matches (start positions) of the text in log.
    This is used in cases where there might be multiple matches in the search area,
    and we want to usually find the closest to the 'supposed_start'.
    """
    matches = []
    search_pos = start
    while True:
        idx = log.find(text, search_pos, end)
        if idx == -1:
            break
        matches.append(idx)
        search_pos = idx + 1  # skip over so we don't find the same match
    return matches


def regex_based_snapping(log: str, snippet: dict, index: int, file: str) -> bool:
    """
    Search for the snippet text in the log using regexes.
    If no matches are found in the small search-window (careful approach),
    the indexes are really broken and we resort to this regex approach.
    """

    def distance(match: re.Match) -> int:
        return abs(match.start() - start)  # lambda m, s=start: abs(m.start() - s)

    start = int(snippet.get("start_index", 0))
    text = str(snippet.get("text", ""))
    escaped_snippet_regex = re.escape(text)
    matches: list[re.Match] = list(re.finditer(escaped_snippet_regex, log))
    if not matches:
        logger.warning("%s[%d] snippet not found", file, index + 1)
        return False
    closest_match = min(matches, key=distance)
    snippet["start_index"] = closest_match.start()
    snippet["end_index"] = closest_match.end()
    return True


def careful_snapping(log: str, snippet: dict, ratio: float, absolute: int) -> bool:
    """
    Adjust snippet indexes based on a local search area around the snippet.

    Example: snippet = consectetur
                                 | ------- |
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do ..."
               misaligned indexes > | -------- |
               we search here > |<<<|          |>>>|
    """

    def distance(pos: int) -> int:
        return abs(pos - supposed_start)  # lambda m, s=supposed_start: abs(m - s)

    supposed_start = int(snippet.get("start_index", 0))
    supposed_end = int(snippet.get("end_index", len(log)))
    text = str(snippet.get("text"))
    start_point = get_search_start(supposed_start, log, ratio, absolute)
    end_point = get_search_end(supposed_end, log, ratio, absolute)
    matches = find_snippet_matches_in_log(log, text, start_point, end_point)
    if matches:
        new_start_index = min(matches, key=distance)
        new_end_index = new_start_index + len(text)
        snippet["start_index"] = new_start_index
        snippet["end_index"] = new_end_index
        return True
    return False


def snap_indexes_to_text(
    json_root_object: dict,
    ratio: float = DEFAULT_RATIO,
    absolute: int = DEFAULT_ABSOLUTE,
) -> int:
    """
    Synchronize the indexes corresponding to the snippet with its log content.

    We search for the snippet text in the log's small area around where the indexes point to.
    By default, this area is expanded on each side by `ratio` % of the full log length.
    If `absolute` is set to a positive number,
    the search area will be expanded by `absolute` chars on each side.

    Return the number of index-adjusted snippets.
    """
    adjusted_snippet_count = 0
    log_dict = json_root_object.get("logs", {})
    if not isinstance(log_dict, dict):
        return adjusted_snippet_count
    for log_name, log_info in log_dict.items():
        if not (isinstance(log_name, str) and isinstance(log_info, dict)):
            continue
        log = log_info.get("content", None)
        snippets = log_info.get("snippets", None)
        if not (isinstance(log, str) and isinstance(snippets, list)):
            continue
        for i, snippet in enumerate(snippets):
            if not check_snippet_fields(snippet, i, log_name, False):
                continue
            snap_worked = careful_snapping(log, snippet, ratio, absolute)
            if snap_worked:
                adjusted_snippet_count += 1
                snap_snippet_to_newline(
                    log, snippet, margin=DEFAULT_MARGIN_FOR_NEWLINE_SNAP
                )
                continue
            logger.warning(
                "%s[%d]: snippet not found in %s around <%d:%d>",
                log_name,
                i + 1,
                f"{absolute} u" if absolute > 0 else f"{int(100 * ratio)} %",
                snippet["start_index"],
                snippet["end_index"],
            )
            regex_worked = regex_based_snapping(log, snippet, i, log_name)
            if regex_worked:
                adjusted_snippet_count += 1
                snap_snippet_to_newline(
                    log, snippet, margin=DEFAULT_MARGIN_FOR_NEWLINE_SNAP
                )
        for i, snippet in enumerate(snippets):
            check_one_snippet(log, i, snippet, log_name, False)

    return adjusted_snippet_count


def skip_false_positives(match: re.Match) -> str:
    """
    Skip matches that are not actual names, like
    `(Amazon Linux)\\n`, `(Parser Generator)\\n`, etc.
    """
    return (
        match.group(0)
        if match.group("pname") in FALSE_POSITIVES_PARENTHESISED_NAMES
        else f"({NAME_PLACEHOLDER})\n"
    )


def skip_false_positives_escaped(match: re.Match) -> str:
    """
    Skip matches that are not actual names,
    but with escaped newline character (reading text as raw)
    """
    return (
        match.group(0)
        if match.group("pname") in FALSE_POSITIVES_PARENTHESISED_NAMES
        else f"({NAME_PLACEHOLDER})\\n"
    )
