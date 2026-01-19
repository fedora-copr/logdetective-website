"""
Functions for best-effort redaction of personal sensitive information from submitted logs.
"""

import logging
from typing import Callable, NamedTuple

import regex as re

from src.constants import LOGGER_NAME


LOGGER = logging.getLogger(LOGGER_NAME)


# Commit Message Header Regex building blocks
YEAR = r"(?P<year>((20|19)[0-9]{2}))"

NICKNAME = r"[\w\\]+"
EMAIL = r"<(?P<email>[\w\.\-\+]+(@|([\[\(][aA][tT][\]\)]))[\w\.\-]+)>"
EMAIL_NOBRACKETS = r"(?P<emailnb>[\w\.\-\+]+(@|([\[\(][aA][tT][\]\)]))[\w\-]+\.[\w\-]+)"

CRLF_NEWLINE = re.compile(r"\r\n")
CR_NEWLINE = re.compile(r"\r")

# Commit Message Header Placeholders
TEMP_MAIL = "#*!copr-team@redhat.com!*#"
TEMP_NAME = "#*!Copr***Team!*#"
# we replace nicknames/fullnames and emails with placeholders using distinct sequences of
# special characters, since the matching process is done in more "phases" over the same string,
# so that we can don't keep replacing and matching the same thing during each step
EMAIL_PLACEHOLDER_REGEX: re.Pattern[str] = re.compile(
    r"\#\*\!copr-team@redhat\.com\!\*\#"
)
NAME_PLACEHOLDER_REGEX: re.Pattern[str] = re.compile(r"\#\*\!Copr\*\*\*Team\!\*\#")
# after everything is done, these placeholders are then replaced with actual valid username/email
EMAIL_CONTACT = "copr-team@redhat.com"
NAME_CONTACT = "Copr Team"

# It seems that standard `re` module is not optimized for handling complex
# regexes and large files. For some log files (>30 MB), using regexes built
# by re+unicodedata (imagine a large OR-chain of all characters from the
# category) takes too long (tens of minutes).
# `regex` takes just a couple of seconds.
UUPPER = r"[\p{Lu}]"
UANY = r"[\p{L}'\-\.]"
UNICODE_FULLNAME = r"((" + UUPPER + UANY + r"*)(?:\s+" + UANY + r"+){1,})"
UNICODE_FULLNAME_CAPITALIZED = (
    r"(" + UUPPER + UANY + r"*)(?:\s+" + UUPPER + UANY + r"*){1,}"
)

# commit msg header date fullname email: ... 2025 John Doe <john.doe@domain.com>
HEADER_DATE_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+" + r"(?P<name>" + UNICODE_FULLNAME + r")\s+" + EMAIL)
)

# commit msg header date nickname email: ... 2025 jdoe123 <jdoe123@domain.com>
# NOTE: we don't check nickname email combination (without preceding date)
# -> this would be too strong, as oftentimes emails can be found also in other parts of the log
HEADER_DATE_NICKNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+(?P<nick>" + NICKNAME + r")\s+" + EMAIL)
)

# Ends of commit messages in spec-files often look like this:
# - done some stuf (John Doe)\n => the newline and parentheses help us catch a lot of names
# - however, there are some false positives, see below
FULLNAME_IN_PARENTHESES_REGEX: re.Pattern[str] = re.compile(
    (r"\(" + r"(?P<pname>" + UNICODE_FULLNAME_CAPITALIZED + r")\)(\n|(\\n))")
)

# Oftentimes you can find someone's full name (or nickname) because it is prefixed by "Author":
# - e.g. Author: John Doe <john.doe@maildomain.com>
AUTHOR_FULLNAME_REGEX: re.Pattern[str] = re.compile(
    (r"Author:\s*" + r"(?P<name>" + UNICODE_FULLNAME + r")\s+" + EMAIL)
)
AUTHOR_NICKNAME_REGEX: re.Pattern[str] = re.compile(
    (r"Author:\s*" + r"(?P<nick>" + NICKNAME + r")\s+" + EMAIL)
)
# commit msg header phase 3 checking -- date email
# 2026  <commit-author@domain.com>
HEADER_DATE_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+(?:" + EMAIL + r"|" + EMAIL_NOBRACKETS + r")")
)
# name surname redaction -> it is possible to find names and surnames within commit messages
# just based on the fact that they are suffixed by the emails in <> brackets, ie.
# Submitted by: John Fitzgerald Doe <john.doe@domain.com>
HEADER_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (r"(?P<name>" + UNICODE_FULLNAME_CAPITALIZED + r")\s+" + EMAIL)
)

EMAIL_REGEX: re.Pattern[str] = re.compile(EMAIL)
RSA_KEY_REGEX: re.Pattern[str] = re.compile(
    r"RSA\s+key\s+(?P<rsa>[0-9A-Fa-f]{32,})", re.IGNORECASE
)
PUBKEY_REGEX: re.Pattern[str] = re.compile(
    r"pubkey\-(?P<pubkey>[0-9a-fA-F]{40})", re.IGNORECASE
)
GPG_FINGERPRINT_REGEX = re.compile(
    (r"Fingerprint:\s*(?P<fingerprint>([0-9a-fA-F]{40})|((\s*[0-9a-fA-F]{4}){10}))"),
    re.IGNORECASE,
)

# When dealing with capitalized fullnames in parentheses in specfile changelog,
# e.g. "- some change made (John Doe)\n", after auditing there were some false positives found,
# which we should not redact, since they (in some special case) might contain useful information
FALSE_POSITIVES_PARENTHESISED_NAMES = set(
    [
        "HTOP Quit",
        "C API",
        "NFS Homedirs",
        "Native Method",
        "MIT OR Unlicense",
        "Unconfiguring CA",
        "Unlicense OR MIT",
        "Not Run",
        "A. S...",
        "AM S..U",
        "AM S.M.",
        "AM S.MU",
        "AM SC..",
        "Tree Builder",
        "Parser Generator",
        "Amazon Linux",
        "Rawhide Prerelease",
        "Heapbuffer Overflow",
        "Forty One",
        "Thirty Nine",
        "Module Device",
        "Processor Device",
        "Processor Aggregator Device",
        "Power Button",
        "Sleep Button",
    ]
)


class SchemaRedactionPipelineStep(NamedTuple):
    """Encapsulate all relevant information about one redaction phase"""

    pattern: re.Pattern
    replacement: str | Callable[[re.Match], str]


# pylint: disable=too-few-public-methods
class SchemaRedactionPipeline:
    """
    A list of RedactionPipelineSteps that are used during sanitization.
    Choose correct regexes and auditing options.
    """

    # pylint: disable=too-many-locals
    def __init__(self):

        # All except last two steps replace with unmatchable placeholders, so we won't
        # overwrite these matches, last two steps replace with actual "placeholders".).
        steps_data = [
            (CRLF_NEWLINE, "\n"),
            (CR_NEWLINE, "\n"),
            (HEADER_DATE_FULLNAME_EMAIL_REGEX, rf"\g<year> {TEMP_NAME} <{TEMP_MAIL}>"),
            (HEADER_DATE_NICKNAME_EMAIL_REGEX, rf"\g<year> {TEMP_NAME} <{TEMP_MAIL}>"),
            (FULLNAME_IN_PARENTHESES_REGEX, skip_false_positives),
            (AUTHOR_FULLNAME_REGEX, f"Author: {TEMP_NAME} <{TEMP_MAIL}>"),
            (AUTHOR_NICKNAME_REGEX, f"Author: {TEMP_NAME} <{TEMP_MAIL}>"),
            (HEADER_DATE_EMAIL_REGEX, rf"\g<year> {TEMP_NAME} <{TEMP_MAIL}>"),
            (HEADER_FULLNAME_EMAIL_REGEX, f"{TEMP_NAME} <{TEMP_MAIL}>"),
            (EMAIL_REGEX, f"<{TEMP_MAIL}>"),
            (RSA_KEY_REGEX, f"RSA key {'FFFF' * 10}"),
            (PUBKEY_REGEX, f"pubkey-{'ffff' * 10}"),
            (GPG_FINGERPRINT_REGEX, f"Fingerprint:{' FFFF' * 10}"),
            # Here we can add other redactions, such as IP addresses, UUIDs, etc.
            (NAME_PLACEHOLDER_REGEX, NAME_CONTACT),
            (EMAIL_PLACEHOLDER_REGEX, EMAIL_CONTACT),
        ]
        self.steps = [
            SchemaRedactionPipelineStep(pattern=p, replacement=r) for p, r in steps_data
        ]


def skip_false_positives(match: re.Match) -> str:
    """
    Skip matches that are not actual names, like
    `(Amazon Linux)\\n`, `(Parser Generator)\\n`, etc.
    """
    return (
        match.group(0)
        if match.group("pname") in FALSE_POSITIVES_PARENTHESISED_NAMES
        else f"({TEMP_NAME})\n"
    )


# instantiate pipeline here, and then in schema redactions (spells.py),
# we will just import it
SANITIZATION_PIPELINE = SchemaRedactionPipeline()
