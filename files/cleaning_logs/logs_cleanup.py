#!/bin/env python3
"""
Main log cleaning and data redaction pipeline.

Note on the shebang: just 'python' doesn't work in container environment.
A local 'dry run' is recommended before running on the persistent storage on the website pod.
You can look what was redacted based on the files in --output_dir OUTDIR.
"""

import logging
import argparse
import json
import os
from typing import cast


from resources import (
    DataCleaningStats,
    DEFAULT_OUTPUTS_PATH,
    DEFAULT_SANITIZATION_OUTPUT,
    DEFAULT_LOGGING_OUTPUT,
)

from utils import (
    check_all_snippets_in_file,
    snap_indexes_to_text,
    add_text_to_snippets,
    files_in_dirs,
    on_all_strings_in_json,
    html_careful_unescape,
    convert_mojibake_to_utf8,
    check_for_broken_escapes,
)

from sanitization import (
    GlobalAuditor,
    sanitize_json_file,
    sanitize_normal_file_raw,
)

logger = logging.getLogger(__name__)


def argparser() -> argparse.Namespace:
    """Parse arguments. The resulting namespace is then cast to MyArguments for IDE support"""

    parser = argparse.ArgumentParser(
        description="Recursive Sanitizer of Personal Data in Logs (with other fixes)"
    )
    parser.add_argument("dir", nargs="+", help="Directories to scan recursively")

    parser.add_argument(
        "--no_auditing",
        action="store_true",
        default=False,
        help=(
            "Turns off storage of redacted entries in a file. Auditing is on by default "
            "and results are stored in OUTPUT_DIR/sanitization_output.txt"
        ),
    )

    parser.add_argument(
        "--escape",
        action="store_true",
        default=False,
        help="The script will keep non-ascii characters as escape sequences in the final logs",
    )

    parser.add_argument(
        "--output_dir",
        default=DEFAULT_OUTPUTS_PATH,
        help="Directory where the logging and auditing info will be saved (default: %(default)s)",
    )

    return parser.parse_args()


# pylint: disable=too-few-public-methods
class MyArguments(argparse.Namespace):
    """Defining arguments for intellisense and IDE"""

    dir: list[str]
    no_auditing: bool
    output_dir: str
    escape: bool


def handle_json_cleaning(
    filename: str,
    args: MyArguments,
    stats: DataCleaningStats,
    audit: GlobalAuditor | None,
) -> None:
    """
    Run the data cleaning and sanitization pipeline for json files.
    Side effect: If the file is not a correct json,
    it will be renamed to .json.borked and will not be cleaned/redacted.
    """
    escape_fix_needed = False
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        escape_fix_needed = check_for_broken_escapes(content)
        json_obj = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        os.rename(filename, f"{filename}.borked")
        return

    # initial snippet check
    broken_snippets = check_all_snippets_in_file(json_obj, filename, warn=False)
    stats.files_with_broken_snippets += broken_snippets > 0
    stats.snippets_broken_initial += broken_snippets

    # adding snippet texts where possible
    new_snippets = add_text_to_snippets(json_obj)
    stats.snippets_added += sum(len(v) for v in new_snippets.values())
    if new_snippets:
        stats.added_snippets_dict[filename] = new_snippets

    # fixing snippets initially

    stats.snippets_reindexed_initial += snap_indexes_to_text(json_obj, absolute=10)

    # fixing broken (mojibake) escape sequences
    json_escape_fix = json_obj
    if escape_fix_needed:
        try:
            json_escape_fix = on_all_strings_in_json(json_obj, convert_mojibake_to_utf8)
        except RuntimeError as e:
            logger.error("escape sequence fixing went wrong: %s", e)
            return
        logger.info("fixed broken escape sequences: %s", filename)
        stats.files_reescaped += 1

    # reverting html escape sequences
    try:
        json_escape_html_fix = on_all_strings_in_json(
            json_escape_fix, html_careful_unescape
        )
    except RuntimeError as e:
        logger.error("html escape fixing went wrong: %s", e)
        return
    if json_escape_fix != json_escape_html_fix:
        logger.info("fixed html sequences: %s", filename)
        stats.files_html_reescaped += 1

    # fixing snippets before redaction
    stats.snippets_reindexed_final += snap_indexes_to_text(
        json_escape_html_fix, ratio=0.02
    )

    # personal data redaction
    redacted_json_obj = sanitize_json_file(json_escape_html_fix, filename, audit=audit)

    # final snippet check
    broken_snippets = check_all_snippets_in_file(redacted_json_obj, filename, warn=True)
    stats.snippets_broken_final += broken_snippets

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(redacted_json_obj, f, indent=4, ensure_ascii=args.escape)
        f.write("\n")
    stats.files_processed += 1  # incrementing only if job is successfully finished


def logs_cleanup() -> None:
    """Main function for cleaning/redacting log files"""
    args = cast(MyArguments, argparser())
    os.makedirs(args.output_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        filename=f"{args.output_dir}/{DEFAULT_LOGGING_OUTPUT}",
        filemode="w",
        format="%(levelname)s [%(funcName)s:%(lineno)d] %(message)s",
        encoding="utf-8",
    )
    stats = DataCleaningStats()
    audit = None if args.no_auditing else GlobalAuditor()

    for filename in files_in_dirs(args.dir, (".json",)):
        handle_json_cleaning(filename, args, stats, audit)

    # with malformed json files, we don't care about fixing snippets or escape sequences,
    # for that we have special regexes... we just want to redact the data inside
    for filename in files_in_dirs(args.dir, (".json.borked",)):
        sanitize_normal_file_raw(filename, audit=audit)
        stats.files_processed += 1

    if audit:
        auditing_log = os.path.join(args.output_dir, DEFAULT_SANITIZATION_OUTPUT)
        with open(auditing_log, "w", encoding="utf-8") as f:
            audit.print_redactions(output=f)
            audit.print_stats(output=f)
    stats.log_stats(args.output_dir)


if __name__ == "__main__":
    logs_cleanup()
