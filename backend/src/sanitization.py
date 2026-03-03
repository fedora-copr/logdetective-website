"""
Functions for best-effort redaction of personal sensitive information from submitted logs.

Regular expressions used during sanitization of uploaded log files.
Some regular expressions have 2 versions - one for reading raw-strings (escaped unicode sequences),
and one for reading strings WITH unicode characters.
The second versions is used on the backend also for sanitization during log upload.
"""

import logging
from typing import Callable, NamedTuple

import regex as re

from src.constants import LOGGER_NAME


LOGGER = logging.getLogger(LOGGER_NAME)

# we use (?:) on groups we don't need to capture
# we use (?>) for atomic grouping -> if the atomic group fails, then the whole pattern fails
# *+ / ++ possessive quantifiers -> if the following pattern fails,
#                                   all the repeated subpatterns will fail as a whole
# ^^ these help with performance, to avoid unnecessary backtracking

# Commit Message Header Regex building blocks
YEAR = r"(?P<year>(?:20|19)[0-9]{2})"

NICKNAME = r"[\w\\]++"

EMAIL = (
    r"\b(?P<email>"
    r"[\w.%+-]++"  # username
    r"(?:@|\([aA][tT]\)|\[[aA][tT]\])"  # "at" symbol
    r"(?:(?>[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)\.){1,10}"  # subdomains
    r"[a-zA-Z]{2,4})\b"  # top level domain
)

# with malformed-json files, we can't parse strings normally, only in raw form,
# and unicode characters were escaped as \uHHHH sequences,
# so in case of unicode characters inside the author's name, we also catch them
UPPERCASE = r"(?:[A-Z]|\\u[0-9a-f]{4})"
ANYCASE = r"(?:[A-Za-z'\-\.]|\\u[0-9a-f]{4})"

FULLNAME = UPPERCASE + ANYCASE + r"*+(?:\s++" + ANYCASE + r"++){1,5}"
FULLNAME_CAPITALIZED = (
    r"(?:" + UPPERCASE + ANYCASE + r"*+)(?:\s++" + UPPERCASE + ANYCASE + r"*+){1,5}"
)

CRLF_NEWLINE_ESCAPED = re.compile(r"\\r\\n")
CR_ESCAPED = re.compile(r"\\r")
CRLF_NEWLINE = re.compile(r"\r\n")
CR_NEWLINE = re.compile(r"\r")

# Commit Message Header Placeholders
EMAIL_PLACEHOLDER = "#*!copr-team@@@redhat.com!*#"
NAME_PLACEHOLDER = "#*!Copr***Team!*#"
# we replace nicknames/fullnames and emails with placeholders using distinct sequences of
# special characters, since the matching process is done in more "phases" over the same string,
# so that we can don't keep replacing and matching the same thing during each step
EMAIL_PLACEHOLDER_REGEX: re.Pattern[str] = re.compile(
    r"\#\*\!copr-team@@@redhat\.com\!\*\#"
)
NAME_PLACEHOLDER_REGEX: re.Pattern[str] = re.compile(r"\#\*\!Copr\*\*\*Team\!\*\#")
# after everything is done, these placeholders are then replaced with actual valid username/email
EMAIL_CONTACT = "copr-team@redhat.com"
NAME_CONTACT = "Copr Team"

# FAS username field (log uploader) inside JSON -> will be replaced by null,
# <indent> and <comma> named groups are needed for anchoring in broken-jsons read as raw text
USERNAME_REGEX = re.compile(
    r"(?P<indent>\s++)\"username\"\:\s*+\"(?P<fas>[^\"]*)\"(?P<comma>,?)\s*+\n"
)

# ASCII-only versions of regexes
# - useful when reading files as raw after json.dump(ascii_only=True)
# ===================================================================


# commit msg header date fullname email: ... 2025 John Doe <john.doe@domain.com>
HEADER_DATE_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    YEAR + r"\s++" + r"(?P<name>" + FULLNAME + r")\s++<" + EMAIL + r">"
)
# commit msg header date nickname email: ... 2025 jdoe123 <jdoe123@domain.com>
# We don't check nickname email combination (without preceding date)
# -> this would be too strong, as oftentimes emails can be found also in other parts of the log
HEADER_DATE_NICKNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    YEAR + r"\s++(?P<nick>" + NICKNAME + r")\s++<" + EMAIL + r">"
)

# Ends of commit messages in spec-files often look like this:
# - done some stuff (John Doe)\n => the newline and parentheses help us catch a lot of names
# - however, there are some false positives, see below
FULLNAME_IN_PARENTHESES_REGEX: re.Pattern[str] = re.compile(
    r"\(" + r"(?P<pname>" + FULLNAME_CAPITALIZED + r")\)\\n"
)

# Oftentimes you can find someone's full name (or nickname) because it is prefixed by "Author":
# - e.g. Author: John Doe <john.doe@maildomain.com>
AUTHOR_FULLNAME_REGEX: re.Pattern[str] = re.compile(
    r"Author:\s*+" + r"(?P<name>" + FULLNAME + r")\s++<" + EMAIL + r">"
)
AUTHOR_NICKNAME_REGEX: re.Pattern[str] = re.compile(
    r"Author:\s*+" + r"(?P<nick>" + NICKNAME + r")\s++<" + EMAIL + r">"
)
# commit msg header phase 3 checking -- date email
# 2026  <commit-author@domain.com> => here, the <> are optional
# A) in HEADER_DATE_EMAIL_REGEX we handle the emails WITH <>
# B) in the following EMAIL_REGEX we also cover the case where email is without <>
HEADER_DATE_EMAIL_REGEX: re.Pattern[str] = re.compile(YEAR + r"\s++<" + EMAIL + r">")
# name surname redaction -> it is possible to find names and surnames within commit messages
# just based on the fact that they are suffixed by the emails in <> brackets, ie.
# Submitted by: John Doe <john.doe@domain.com>
HEADER_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    r"(?P<name>" + FULLNAME_CAPITALIZED + r")\s++<" + EMAIL + r">"
)
EMAIL_REGEX: re.Pattern[str] = re.compile(EMAIL)
RSA_KEY_REGEX: re.Pattern[str] = re.compile(
    r"RSA\s++key\s++(?P<rsa>[0-9A-F]{16,512})", re.IGNORECASE
)
PUBKEY_REGEX: re.Pattern[str] = re.compile(
    r"pubkey\-(?P<pubkey>[0-9A-F]{8}[0-9A-F-]{8,128})", re.IGNORECASE
)
GPG_FINGERPRINT_REGEX = re.compile(
    r"Fingerprint:\s*+(?P<fingerprint>[0-9A-F]{32,64}|(?:\s*+[0-9A-F]{4}){8,16})",
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

# Unicode-specific regexes
# - when reading strings before dumping into json (non-escaped unicode)
# =====================================================================

# It seems that standard `re` module is not optimized for handling complex
# regexes and large files. For some log files (>30 MB), using regexes built
# by re+unicodedata (imagine a large OR-chain of all characters from the
# category) takes too long (tens of minutes).
# `regex` takes just a couple of seconds.

UUPPER = r"\p{Lu}"
UANY = r"[\p{L}'\-\.]"

UNICODE_FULLNAME = r"(?:" + UUPPER + UANY + r"*+)(?:\s++" + UANY + r"++){1,5}"
UNICODE_FULLNAME_CAPITALIZED = (
    r"(?:" + UUPPER + UANY + r"*+)(?:\s++" + UUPPER + UANY + r"*+){1,5}"
)

UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    YEAR + r"\s++" + r"(?P<name>" + UNICODE_FULLNAME + r")\s++<" + EMAIL + r">"
)
UNICODE_FULLNAME_IN_PARENTHESES_REGEX: re.Pattern[str] = re.compile(
    r"\(" + r"(?P<pname>" + UNICODE_FULLNAME_CAPITALIZED + r")\)(?:\n|\\n)"
)
UNICODE_AUTHOR_FULLNAME_REGEX: re.Pattern[str] = re.compile(
    r"Author:\s*+" + r"(?P<name>" + UNICODE_FULLNAME + r")\s++<" + EMAIL + r">"
)
UNICODE_HEADER_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    r"(?P<name>" + UNICODE_FULLNAME_CAPITALIZED + r")\s++<" + EMAIL + r">"
)

# Resources for sanitization during upload on website's backend
# =============================================================


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
            (
                UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX,
                rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (
                HEADER_DATE_NICKNAME_EMAIL_REGEX,
                rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (UNICODE_FULLNAME_IN_PARENTHESES_REGEX, skip_false_positives),
            (
                UNICODE_AUTHOR_FULLNAME_REGEX,
                f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (
                AUTHOR_NICKNAME_REGEX,
                f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (
                HEADER_DATE_EMAIL_REGEX,
                rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (
                UNICODE_HEADER_FULLNAME_EMAIL_REGEX,
                f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            ),
            (EMAIL_REGEX, f"{EMAIL_PLACEHOLDER}"),
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
        else f"({NAME_PLACEHOLDER})\n"
    )


# instantiate pipeline here, and then in schema redactions (spells.py),
# we will just import it
SANITIZATION_PIPELINE = SchemaRedactionPipeline()
