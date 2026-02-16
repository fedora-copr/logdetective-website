"""
Regular expressions used during sanitization of uploaded log files.

Some regular expressions have 2 versions - one for reading raw-strings (escaped unicode sequences),
and one for reading strings WITH unicode characters.
"""

import regex as re

# Commit Message Header Regex building blocks
YEAR = r"(?P<year>((20|19)[0-9]{2}))"

NICKNAME = r"[\w\\]+"
EMAIL = r"<(?P<email>[\w\.\-\+]+(@|([\[\(][aA][tT][\]\)]))[\w\.\-]+)>"
EMAIL_NOBRACKETS = r"(?P<emailnb>[\w\.\-\+]+(@|([\[\(][aA][tT][\]\)]))[\w\-]+\.[\w\-]+)"

# in case of unicode characters inside the author's name, we also catch hexa \uHHHH sequences
UPPERCASE = r"([A-Z]|(\\u[0-9a-f]{4}))"
ANYCASE = r"([A-Za-z'\-\.]|(\\u[0-9a-f]{4}))"
FULLNAME = r"((" + UPPERCASE + ANYCASE + r"*)(?:\s+" + ANYCASE + r"+){1,})"
FULLNAME_CAPITALIZED = (
    r"(" + UPPERCASE + ANYCASE + r"*)(?:\s+" + UPPERCASE + ANYCASE + r"*){1,}"
)

CRLF_NEWLINE_ESCAPED = re.compile(r"\\r\\n")
CR_ESCAPED = re.compile(r"\\r")
CRLF_NEWLINE = re.compile(r"\r\n")
CR_NEWLINE = re.compile(r"\r")

# Commit Message Header Placeholders
EMAIL_PLACEHOLDER = "#*!copr-team@redhat.com!*#"
NAME_PLACEHOLDER = "#*!Copr***Team!*#"
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

# FAS username field (log uploader) inside JSON -> will be replaced by null
USERNAME_REGEX = re.compile(
    r"(?P<indent>\s+)\"username\"\:\s*\"(.*)\"(?P<comma>,?)\s*\n"
)

# ASCII-only versions of regexes
# - useful when reading files as raw after json.dump(ascii_only=True)
# ===================================================================


# commit msg header date fullname email: ... 2025 John Doe <john.doe@domain.com>
HEADER_DATE_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+" + r"(?P<name>" + FULLNAME + r")\s+" + EMAIL)
)
# commit msg header date nickname email: ... 2025 jdoe123 <jdoe123@domain.com>
# NOTE: we don't check nickname email combination (without preceding date)
# -> this would be too strong, as oftentimes emails can be found also in other parts of the log
HEADER_DATE_NICKNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+(?P<nick>" + NICKNAME + r")\s+" + EMAIL)
)
FULLNAME_IN_PARENTHESES_REGEX: re.Pattern[str] = re.compile(
    (r"\(" + r"(?P<pname>" + FULLNAME_CAPITALIZED + r")\)\\n")
)
AUTHOR_FULLNAME_REGEX: re.Pattern[str] = re.compile(
    (r"Author:\s*" + r"(?P<name>" + FULLNAME + r")\s+" + EMAIL)
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
# Submitted by: John Doe <john.doe@domain.com>
HEADER_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (r"(?P<name>" + FULLNAME_CAPITALIZED + r")\s+" + EMAIL)
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

# Unicode-specific regexes
# - when reading strings before dumping into json (non-escaped unicode)
# =====================================================================

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

UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (YEAR + r"\s+" + r"(?P<name>" + UNICODE_FULLNAME + r")\s+" + EMAIL)
)
UNICODE_FULLNAME_IN_PARENTHESES_REGEX: re.Pattern[str] = re.compile(
    (r"\(" + r"(?P<pname>" + UNICODE_FULLNAME_CAPITALIZED + r")\)(\n|(\\n))")
)
UNICODE_AUTHOR_FULLNAME_REGEX: re.Pattern[str] = re.compile(
    (r"Author:\s*" + r"(?P<name>" + UNICODE_FULLNAME + r")\s+" + EMAIL)
)
UNICODE_HEADER_FULLNAME_EMAIL_REGEX: re.Pattern[str] = re.compile(
    (r"(?P<name>" + UNICODE_FULLNAME_CAPITALIZED + r")\s+" + EMAIL)
)
