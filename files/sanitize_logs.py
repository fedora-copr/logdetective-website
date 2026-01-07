#!/bin/env python3
"""
A script for best-effort redaction of personal sensitive information from submitted logs.

Note on the shebang: just 'python' doesn't work in container environment
A local 'dry run' is recommended before running on the persistent storage on the website pod.
You can look what was redacted based on the --out OUTFILE.
"""

import os
import re
import argparse
from collections import namedtuple


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

# Commit Message Header Placeholders
EMAIL_PLACEHOLDER = "#*!copr-team@redhat.com!*#"
NAME_PLACEHOLDER = "#*!Copr***Team!*#"
# we replace nicknames/fullnames and emails with placeholders using distinct sequences of
# special characters, since the matching process is done in more "phases" over the same string,
# so that we can don't keep replacing and matching the same thing during each step
EMAIL_PLACEHOLDER_REGEX = re.compile(r"\#\*\!copr-team@redhat\.com\!\*\#")
NAME_PLACEHOLDER_REGEX = re.compile(r"\#\*\!Copr\*\*\*Team\!\*\#")
# after everything is done, these placeholders are then replaced with actual valid username/email
EMAIL_CONTACT = "copr-team@redhat.com"
NAME_CONTACT = "Copr Team"


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


class Auditor:
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
        # so far i only care about the first entry
        if string not in self.data:
            self.data[string] = AuditEntry(logfile=logfile, fullmatch=match)


# Keep some debug info for each unique piece of redacted data.
AuditEntry = namedtuple("AuditEntry", ["logfile", "fullmatch"])


stats = RedactionStats()
date_fullname_auditor = Auditor(
    "Fullnames, w/ date and email (from commit headers)", stats
)
fullname_auditor = Auditor(
    "Capitalized Fullnames, no preceding date and following email", stats
)
parenthesised_name_auditor = Auditor("Parenthesised fullnames", stats)
nickname_auditor = Auditor("Nicknames, w/ date and email (from commit headers)", stats)
email_auditor = Auditor("Emails", stats)
rsa_key_auditor = Auditor("RSA keys", stats)
pubkey_auditor = Auditor("Pubkeys", stats)
gpg_fingerprint_auditor = Auditor("GPG Fingerprints", stats)
ipv4_address_auditor = Auditor("IPV4 Addresses", stats)  # unused
uuid_auditor = Auditor("UUIDs", stats)  # unused


HEADER_DATE_FULLNAME_EMAIL_REGEX = re.compile(
    (  # phase 1 checking - date fullname email
        YEAR + r"\s+" + r"(?P<name>" + FULLNAME + r")\s+" + EMAIL
    )
)


def date_fullname_email_redaction(file_path: str, value: str) -> str:
    """Redact info based on commit message headers ... YEAR FULL NAME <email> ..."""
    placeholder = r"\g<year> " + f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"

    for match in HEADER_DATE_FULLNAME_EMAIL_REGEX.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        date_fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return HEADER_DATE_FULLNAME_EMAIL_REGEX.sub(placeholder, value)


# NOTE: we don't check nickname email combination (without preceding date)
# -> this would be too strong, as oftentimes emails can be found also in other parts of the log
HEADER_DATE_NICKNAME_EMAIL_REGEX = re.compile(
    (  # phase 2 checking - date nickname email
        YEAR + r"\s+(?P<nick>" + NICKNAME + r")\s+" + EMAIL
    )
)


def date_nickname_email_redaction(file_path: str, value: str) -> str:
    """
    Redact info based on commit message headers: ... YEAR NICKNAME <email> ...
    Full name is using Capitalized Words. Nickname can contain any printable characters.
    """
    placeholder = r"\g<year> " + f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"

    for match in HEADER_DATE_NICKNAME_EMAIL_REGEX.finditer(value):
        matched_nick = match.group("nick")
        matched_email = match.group("email")
        nickname_auditor.insert(matched_nick, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return HEADER_DATE_NICKNAME_EMAIL_REGEX.sub(placeholder, value)


FULLNAME_IN_PARENTHESES_REGEX = re.compile(
    (r"\(" + r"(?P<name>" + FULLNAME_CAPITALIZED + r")\)\\n")
)


def fullname_parentheses_redaction(file_path: str, value: str) -> str:
    """
    Redact info based on commit message footers containing only fullname in parentheses.
    A lot of commit messages follow this pattern: 'Done some stuff (Name Surname)\n'.
    """
    # some false positives have been found and since there is a lot of actual fullnames,
    # it wass deemed better to just skip the found false positives, than not use this at all
    false_positives = set(
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
            "Module Device",
            "Processor Device",
            "Processor Aggregator Device",
            "Power Button",
            "Sleep Button",
        ]
    )

    placeholder = f"({NAME_PLACEHOLDER})\\n"

    def redact_callback(match: re.Match[str]):
        full_match = match.group(0)
        matched_name = match.group("name")
        if matched_name in false_positives:
            return full_match
        parenthesised_name_auditor.insert(matched_name, file_path, full_match)
        return f"{placeholder}"

    return FULLNAME_IN_PARENTHESES_REGEX.sub(redact_callback, value)


AUTHOR_FULLNAME_REGEX = re.compile(
    (r"Author:\s*" + r"(?P<name>" + FULLNAME + r")\s+" + EMAIL)
)


def author_fullname_email_redaction(file_path: str, value: str) -> str:
    """Redact commit messages containing pattern "Author: Full Name <email>"."""
    placeholder = f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in AUTHOR_FULLNAME_REGEX.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return AUTHOR_FULLNAME_REGEX.sub(placeholder, value)


AUTHOR_NICKNAME_REGEX = re.compile(
    (r"Author:\s*" + r"(?P<nick>" + NICKNAME + r")\s+" + EMAIL)
)


def author_nickname_email_redaction(file_path: str, value: str) -> str:
    """Redact commit messages containing pattern "Author: nickname <email>"."""
    placeholder = f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in AUTHOR_NICKNAME_REGEX.finditer(value):
        matched_nick = match.group("nick")
        matched_email = match.group("email")
        nickname_auditor.insert(matched_nick, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return AUTHOR_NICKNAME_REGEX.sub(placeholder, value)


HEADER_DATE_EMAIL_REGEX = re.compile(
    (  # commit msg header phase 2 checking -- date email
        YEAR + r"\s+(?:" + EMAIL + r"|" + EMAIL_NOBRACKETS + r")"
    )
)


def date_email_redaction(file_path: str, value: str) -> str:
    """Redact info based on commit message headers: ... YEAR  <email> ... (username is skipped)"""
    placeholder = r"\g<year> " + f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in HEADER_DATE_EMAIL_REGEX.finditer(value):
        matched_email = match.group("email") or match.group("emailnb")
        email_auditor.insert(matched_email, file_path, match.group(0))
    return HEADER_DATE_EMAIL_REGEX.sub(placeholder, value)


# name surname redaction -> it is possible to find names and surnames within commit messages
# just based on the fact that they are suffixed by the emails in <> brackets, ie.
# Submitted by: John Doe <john.doe@domain.com>
HEADER_FULLNAME_EMAIL_REGEX = re.compile(
    (  # commit msg phase 3 checking -- fullname email
        r"(?P<name>" + FULLNAME_CAPITALIZED + r")\s+" + EMAIL
    )
)


def fullname_email_redaction(file_path: str, value: str) -> str:
    """Redact info based on pattern "Fullname Capitalized <email>"."""
    placeholder = f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in HEADER_FULLNAME_EMAIL_REGEX.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return HEADER_FULLNAME_EMAIL_REGEX.sub(placeholder, value)


EMAIL_REGEX = re.compile(EMAIL)


def email_redaction(file_path: str, value: str) -> str:
    """Redact emails enclosed in angle brackets <email@domain.com>"""
    placeholder = f"<{EMAIL_PLACEHOLDER}>"
    for match in EMAIL_REGEX.finditer(value):
        matched_email = match.group("email")
        email_auditor.insert(matched_email, file_path, match.group(0))
    return EMAIL_REGEX.sub(placeholder, value)


RSA_KEY_REGEX = re.compile(r"RSA\s+key\s+(?P<rsa>[0-9A-Fa-f]{32,})", re.IGNORECASE)


def rsa_key_redaction(file_path: str, value: str) -> str:
    """Redact public RSA keys."""
    placeholder = f"RSA key {'FFFF' * 10}"
    for match in RSA_KEY_REGEX.finditer(value):
        matched_key = match.group("rsa")
        rsa_key_auditor.insert(matched_key, file_path, match.group(0))
    return RSA_KEY_REGEX.sub(placeholder, value)


PUBKEY_REGEX = re.compile(r"pubkey\-(?P<pubkey>[0-9a-fA-F]{40})", re.IGNORECASE)


def pubkey_redaction(file_path: str, value: str):
    """Redact strings following the pattern pubkey-40_hexa_character_string."""
    placeholder = f"pubkey-{'ffff' * 10}"
    for match in PUBKEY_REGEX.finditer(value):
        matched_key = match.group("pubkey")
        pubkey_auditor.insert(matched_key, file_path, match.group(0))
    return PUBKEY_REGEX.sub(placeholder, value)


GPG_FINGERPRINT_REGEX = re.compile(
    (r"Fingerprint:\s*(?P<fingerprint>([0-9a-fA-F]{40})|((\s*[0-9a-fA-F]{4}){10}))"),
    re.IGNORECASE,
)


def gpg_fingerprint_redaction(file_path: str, value: str):
    """Redact GPG fingerprints."""
    placeholder = f"Fingerprint:{' FFFF' * 10}"
    for match in GPG_FINGERPRINT_REGEX.finditer(value):
        matched_key = match.group("fingerprint")
        gpg_fingerprint_auditor.insert(matched_key, file_path, match.group(0))
    return GPG_FINGERPRINT_REGEX.sub(placeholder, value)


# IPV4_REGEX = re.compile(
#     r"[Ii][Pp]:\s+(?P<ipv4>[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})"
# )


# def ipv4_address_redaction(file_path: str, value: str):
#     """Redact IPV4 addresses. (unused)"""
#     placeholder = f"IP: 0.0.0.0"
#     for match in IPV4_REGEX.finditer(value):
#         matched_ip = match.group("ipv4")
#         ipv4_address_auditor.insert(matched_ip, file_path, match.group(0))
#     return IPV4_REGEX.sub(placeholder, value)


# def uuid_redaction(file_path: str, value: str):
#     """Redact UUIDs. (unused)"""
#     pass


def sanitize_string(file_path: str, value: str) -> str:
    """Run the whole personal data redaction pipeline."""
    if not isinstance(value, str):
        return value

    redaction_pipeline = [
        date_fullname_email_redaction,
        date_nickname_email_redaction,
        fullname_parentheses_redaction,
        author_fullname_email_redaction,
        author_nickname_email_redaction,
        date_email_redaction,
        fullname_email_redaction,
        email_redaction,
        rsa_key_redaction,
        gpg_fingerprint_redaction,
        pubkey_redaction,
        # ipv4_address_redaction,
        # uuid_redaction,
    ]

    for func in redaction_pipeline:
        value = func(file_path, value)

    # change name and email placeholders to copr team contacts
    value = NAME_PLACEHOLDER_REGEX.sub(NAME_CONTACT, value)
    value = EMAIL_PLACEHOLDER_REGEX.sub(EMAIL_CONTACT, value)

    return value


USERNAME_REGEX = re.compile(
    r"(?P<indent>\s+)\"username\"\:\s*\"(.*)\"(?P<comma>,?)\s*\n"
)


def sanitize_normal_file(file_path: str) -> None:
    """
    Sanitize all personal data of a file (JSON read as a raw-text).

    Remove the content of the "username" field and in the string fields,
    run the sanitization/redaction pipeline.
    """
    q = '"'
    username_placeholder = rf"\g<indent>{q}username{q}: null\g<comma>\n"
    with open(file_path, "r", encoding="ascii") as f:
        content = f.readlines()
        redacted_content = []
        for _, line in enumerate(content):
            if re.match(USERNAME_REGEX, line):
                redacted_username = USERNAME_REGEX.sub(username_placeholder, line)
                redacted_content.append(redacted_username)
                continue
            redacted_content.append(sanitize_string(file_path, line))
    with open(file_path, "w", encoding="ascii") as f:
        f.write("".join(redacted_content))


def sanitize_directory(path: str):
    """Recursive calling of single file sanitization."""
    for root, _, files in os.walk(path):
        for file_name in files:
            if not any(
                [file_name.endswith(".json"), file_name.endswith(".json.borked")]
            ):
                continue
            sanitize_normal_file(os.path.join(root, file_name))
            stats.add_file()


def main(arguments: argparse.Namespace):
    """Recursively find all JSON files, run the sanitization pipeline and keep some statistics."""
    try:
        for path in arguments.dir:
            if not os.path.isdir(path):
                print(f"{path} is not a reachable directory, skipping")
                continue
            sanitize_directory(path)
    except KeyboardInterrupt:
        print("Keyboard Interrupt: printing the logged sanitized stats ...")

    auditors = [
        date_fullname_auditor,
        fullname_auditor,
        parenthesised_name_auditor,
        nickname_auditor,
        email_auditor,
        rsa_key_auditor,
        gpg_fingerprint_auditor,
        pubkey_auditor,
    ]

    if arguments.out is not None:
        with open(arguments.out, "w", encoding="ascii") as f:
            for auditor in auditors:
                print(auditor, file=f)
            print(f"All redactions = {stats.total_redactions}", file=f)

    # in any case, redaction statistics will get printed (to stdout):
    for auditor in auditors:
        print(auditor.desc, auditor.count)
    print(f"Total redactions {stats.total_redactions}")
    print(f"Total files {stats.total_files}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Recursive Sanitizer of Personal Data in Logs"
    )
    parser.add_argument("dir", nargs="+", help="Directories to scan recursively")
    parser.add_argument(
        "--out",
        default=None,
        help="Name of the output file (where redactable information is listed - optional)",
    )
    args = parser.parse_args()
    main(args)
