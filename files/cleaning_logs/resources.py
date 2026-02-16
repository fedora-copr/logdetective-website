"""
Class definitions, constants and other resources used all across the data cleaning/redactions.
"""

import os
import sys
import json
import logging

from typing import Callable, NamedTuple

import regex as re


logger = logging.getLogger(__name__)


# output files directory:
DEFAULT_OUTPUTS_PATH = "./outputs"
DEFAULT_SANITIZATION_OUTPUT = "sanitization_output.txt"
DEFAULT_LOGGING_OUTPUT = "output.log"
DEFAULT_SNIPPET_ADDED = "snippets_added.json"

# expand search area for snippets by (DEFAULT_RATIO * 100) % of the log's length
DEFAULT_RATIO = 0.0

# expand search area by DEFAULT_ABSOLUTE characters to the each side of the
# snippet for index-snapping, if negative, then DEFAULT_RATIO is used
DEFAULT_ABSOLUTE = -1


UNICODE_ESCAPE_BY_BYTE_UTF8: re.Pattern = re.compile(
    r"\\u00(c[2-9a-f]|e[0-9a-f]|f[0-4])(\\u00[8-9a-b][0-9a-f])+", re.IGNORECASE
)

# we ignore snippets that would be 5 and less characters long,
# as they probably don't contain any useful information
SNIPPET_LENGTH_THRESHOLD = 5

# defines the area (in characters) around the snippet for which we try to find newlines
# and adjust the snippets such that they contain the whole lines from the log,
# since the indexes are often off-by-one and inferred snippet texts might look weird,
# e.g. "\nE[rror: Something happene]d\n" instead of "\n[Error: Something happened]\n"
DEFAULT_MARGIN_FOR_NEWLINE_SNAP = 5


class RedactionStats:
    """Top-level statistics."""

    def __init__(self):
        self.total_redactions = 0
        self.total_files = 0

    def add_redaction(self):
        """Increment redaction count."""
        self.total_redactions += 1

    def add_file(self):
        """Increment analyzed (redacted) file count."""
        self.total_files += 1


class AuditEntry(NamedTuple):
    """For each redacted string we store where we found it (first match) and what was matched"""

    logfile: str
    fullmatch: str | re.Match


class SpecificAuditor:
    """Remember all unique strings that were matched so that we can check redactions."""

    def __init__(self, desc: str, statistics: RedactionStats):
        self.data: dict[str, AuditEntry] = {}
        self.count: int = 0
        self.desc: str = desc
        self.stats: RedactionStats = statistics

    def __repr__(self):
        result = "=" * (len(self.desc) + 6) + "\n"
        result += f"== {self.desc} ==" + "\n"
        result += "=" * (len(self.desc) + 6) + "\n"
        for match, entry in self.data.items():
            matchstr = match.replace("\n", " ").replace("\t", " ")
            entrystr = entry.fullmatch.replace("\n", " ").replace("\t", " ")
            result += f"{matchstr:<50} fullmatch: {entrystr:<70}" + "\n"
        result += f"Number of matches = {self.count}" + "\n"
        return result

    def insert(self, string: str, logfile: str, match: str):
        """Remember all distinct 'redacted strings' first occurence
        with the file where it was found and full matched string"""
        self.stats.add_redaction()
        self.count += 1
        # when auditing, it is sufficient to only care about the first entry
        if string not in self.data:
            self.data[string] = AuditEntry(logfile=logfile, fullmatch=match)


# pylint: disable=too-many-instance-attributes
class GlobalAuditor:
    """Encapsulate all auditing objects into one place"""

    def __init__(self):
        self.stats = RedactionStats()
        self.date_fullnames = SpecificAuditor(
            "Fullnames, w/ date and email (from commit headers)", self.stats
        )
        self.fullnames = SpecificAuditor(
            "Capitalized Fullnames, no preceding date and following email", self.stats
        )
        self.parenthesised_names = SpecificAuditor(
            "Parenthesised fullnames", self.stats
        )
        self.nicknames = SpecificAuditor(
            "Nicknames, w/ date and email (from commit headers)", self.stats
        )
        self.emails = SpecificAuditor("Emails", self.stats)
        self.rsa_keys = SpecificAuditor("RSA keys", self.stats)
        self.pubkeys = SpecificAuditor("Pubkeys", self.stats)
        self.gpg_fingerprints = SpecificAuditor("GPG Fingerprints", self.stats)

    def print_redactions(self, output=sys.stdout):
        """Print all (unique) redacted items, for debug purposes"""
        for item in self.__dict__.values():
            if not isinstance(item, SpecificAuditor):
                continue
            print(item, file=output)
        self.print_stats(output=output)

    def print_stats(self, output=sys.stdout):
        """Print some stats about redactions"""
        print(f"Total redactions = {self.stats.total_redactions}", file=output)
        print(f"Total files = {self.stats.total_files}", file=output)


class RedactionPipelineStep(NamedTuple):
    """Encapsulate all relevant information about one redaction phase"""

    pattern: re.Pattern
    replacement: str | Callable[[re.Match], str]
    auditing: dict[str, SpecificAuditor]  # group names -> where to store auditing info


# pylint: disable=too-many-instance-attributes
class DataCleaningStats:
    """Encapsulate statistics about file and snippet cleaning"""

    def __init__(self) -> None:
        self.files_with_broken_snippets: int = 0
        self.snippets_broken_initial: int = 0
        self.snippets_added: int = 0
        self.snippets_reindexed_initial: int = 0
        self.files_reescaped: int = 0
        self.files_html_reescaped: int = 0
        self.snippets_reindexed_final: int = 0
        self.snippets_broken_final: int = 0
        self.files_processed: int = 0
        self.added_snippets_dict: dict[str, dict[str, list[str]]] = {}

    def log_stats(self, where: str = DEFAULT_OUTPUTS_PATH):
        """For debug purposes"""
        with open(
            os.path.join(where, DEFAULT_SNIPPET_ADDED), "w", encoding="utf-8"
        ) as f:
            json.dump(self.added_snippets_dict, f, ensure_ascii=False, indent=4)
            f.write("\n")

        logger.info(
            "Files with broken snippets (initially): %d",
            self.files_with_broken_snippets,
        )
        logger.info("Broken snippets (initially): %d", self.snippets_broken_initial)
        logger.info("Added snippets: %d", self.snippets_added)
        logger.info("Snippets reindexed initially: %d", self.snippets_reindexed_initial)
        logger.info("Files with fixed escapes: %d", self.files_reescaped)
        logger.info("Files with fixed htmls: %d", self.files_html_reescaped)
        logger.info(
            "Snippets reindexed before sanitization: %d", self.snippets_reindexed_final
        )
        logger.info("Broken snippets (final): %d", self.snippets_broken_final)
        logger.info("Files processed: %d", self.files_processed)

    def reset_stats(self):
        """Reinitialize stats (except for added snippet dictionary)"""
        self.files_with_broken_snippets = 0
        self.snippets_broken_initial = 0
        self.snippets_added = 0
        self.snippets_reindexed_initial = 0
        self.files_reescaped = 0
        self.files_html_reescaped = 0
        self.snippets_reindexed_final = 0
        self.snippets_broken_final = 0
        self.files_processed = 0
