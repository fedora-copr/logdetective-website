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

from src.regexes_sanitization import (
    EMAIL_PLACEHOLDER,
    NAME_PLACEHOLDER,
    EMAIL_PLACEHOLDER_REGEX,
    NAME_PLACEHOLDER_REGEX,
    EMAIL_CONTACT,
    NAME_CONTACT,
    HEADER_DATE_FULLNAME_EMAIL_REGEX,
    UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX,
    HEADER_DATE_NICKNAME_EMAIL_REGEX,
    UNICODE_FULLNAME_IN_PARENTHESES_REGEX,
    FULLNAME_IN_PARENTHESES_REGEX,
    AUTHOR_FULLNAME_REGEX,
    UNICODE_AUTHOR_FULLNAME_REGEX,
    AUTHOR_NICKNAME_REGEX,
    HEADER_DATE_EMAIL_REGEX,
    HEADER_FULLNAME_EMAIL_REGEX,
    UNICODE_HEADER_FULLNAME_EMAIL_REGEX,
    EMAIL_REGEX,
    RSA_KEY_REGEX,
    PUBKEY_REGEX,
    GPG_FINGERPRINT_REGEX,
    USERNAME_REGEX,
)


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


def date_fullname_email_redaction(file_path: str, value: str, escaped=True) -> str:
    """Redact info based on commit message headers ... YEAR FULL NAME <email> ..."""
    placeholder = r"\g<year> " + f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    used_regex = (
        HEADER_DATE_FULLNAME_EMAIL_REGEX
        if escaped
        else UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX
    )
    for match in used_regex.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        date_fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return used_regex.sub(placeholder, value)


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


def fullname_parentheses_redaction(file_path: str, value: str, escaped=True) -> str:
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

    placeholder = f"({NAME_PLACEHOLDER})\n"

    def redact_callback(match: re.Match[str]):
        full_match = match.group(0)
        matched_name = match.group("name")
        if matched_name in false_positives:
            return full_match
        parenthesised_name_auditor.insert(matched_name, file_path, full_match)
        return f"{placeholder}"

    used_regex = (
        FULLNAME_IN_PARENTHESES_REGEX
        if escaped
        else UNICODE_FULLNAME_IN_PARENTHESES_REGEX
    )
    return used_regex.sub(redact_callback, value)


def author_fullname_email_redaction(file_path: str, value: str, escaped=True) -> str:
    """Redact commit messages containing pattern "Author: Full Name <email>"."""
    placeholder = f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    used_regex = AUTHOR_FULLNAME_REGEX if escaped else UNICODE_AUTHOR_FULLNAME_REGEX
    for match in used_regex.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return used_regex.sub(placeholder, value)


def author_nickname_email_redaction(file_path: str, value: str) -> str:
    """Redact commit messages containing pattern "Author: nickname <email>"."""
    placeholder = f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in AUTHOR_NICKNAME_REGEX.finditer(value):
        matched_nick = match.group("nick")
        matched_email = match.group("email")
        nickname_auditor.insert(matched_nick, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return AUTHOR_NICKNAME_REGEX.sub(placeholder, value)


def date_email_redaction(file_path: str, value: str) -> str:
    """Redact info based on commit message headers: ... YEAR  <email> ... (username is skipped)"""
    placeholder = r"\g<year> " + f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    for match in HEADER_DATE_EMAIL_REGEX.finditer(value):
        matched_email = match.group("email") or match.group("emailnb")
        email_auditor.insert(matched_email, file_path, match.group(0))
    return HEADER_DATE_EMAIL_REGEX.sub(placeholder, value)


def fullname_email_redaction(file_path: str, value: str, escaped=True) -> str:
    """Redact info based on pattern "Fullname Capitalized <email>"."""
    placeholder = f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>"
    used_regex = (
        HEADER_FULLNAME_EMAIL_REGEX if escaped else UNICODE_HEADER_FULLNAME_EMAIL_REGEX
    )
    for match in used_regex.finditer(value):
        matched_name = match.group("name")
        matched_email = match.group("email")
        fullname_auditor.insert(matched_name, file_path, match.group(0))
        email_auditor.insert(matched_email, file_path, match.group(0))
    return used_regex.sub(placeholder, value)


def email_redaction(file_path: str, value: str) -> str:
    """Redact emails enclosed in angle brackets <email@domain.com>"""
    placeholder = f"<{EMAIL_PLACEHOLDER}>"
    for match in EMAIL_REGEX.finditer(value):
        matched_email = match.group("email")
        email_auditor.insert(matched_email, file_path, match.group(0))
    return EMAIL_REGEX.sub(placeholder, value)


def rsa_key_redaction(file_path: str, value: str) -> str:
    """Redact public RSA keys."""
    placeholder = f"RSA key {'FFFF' * 10}"
    for match in RSA_KEY_REGEX.finditer(value):
        matched_key = match.group("rsa")
        rsa_key_auditor.insert(matched_key, file_path, match.group(0))
    return RSA_KEY_REGEX.sub(placeholder, value)


def pubkey_redaction(file_path: str, value: str):
    """Redact strings following the pattern pubkey-40_hexa_character_string."""
    placeholder = f"pubkey-{'ffff' * 10}"
    for match in PUBKEY_REGEX.finditer(value):
        matched_key = match.group("pubkey")
        pubkey_auditor.insert(matched_key, file_path, match.group(0))
    return PUBKEY_REGEX.sub(placeholder, value)


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


# def ipv4_address_redaction(file_path: str, value: str) -> str:
#     """Redact IPV4 addresses. (unused)"""
#     placeholder = f"IP: 0.0.0.0"
#     for match in IPV4_REGEX.finditer(value):
#         matched_ip = match.group("ipv4")
#         ipv4_address_auditor.insert(matched_ip, file_path, match.group(0))
#     return IPV4_REGEX.sub(placeholder, value)


# def uuid_redaction(file_path: str, value: str) -> str:
#     """Redact UUIDs. (unused)"""
#     pass


def sanitize_string(file_path: str, value: str, ascii_only=False) -> str:
    """Run the whole personal data redaction pipeline."""
    if not isinstance(value, str):
        return value

    value = date_fullname_email_redaction(file_path, value, escaped=ascii_only)
    value = date_nickname_email_redaction(file_path, value)
    value = fullname_parentheses_redaction(file_path, value, escaped=ascii_only)
    value = author_fullname_email_redaction(file_path, value, escaped=ascii_only)
    value = author_nickname_email_redaction(file_path, value)
    value = date_email_redaction(file_path, value)
    value = fullname_email_redaction(file_path, value, escaped=ascii_only)
    value = email_redaction(file_path, value)
    value = rsa_key_redaction(file_path, value)
    value = gpg_fingerprint_redaction(file_path, value)
    value = pubkey_redaction(file_path, value)
    # value = ipv4_address_redaction(file_path, value)
    # value = uuid_redaction(file_path, value)

    # change name and email placeholders to copr team contacts
    value = NAME_PLACEHOLDER_REGEX.sub(NAME_CONTACT, value)
    value = EMAIL_PLACEHOLDER_REGEX.sub(EMAIL_CONTACT, value)

    return value


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
            redacted_content.append(sanitize_string(file_path, line, ascii_only=True))
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
    """
    Recursively find all JSON files, run the sanitization pipeline and keep some statistics.

    Default: ascii_only=True => When the script is run directly, it defaults to this.
    i.e. treat Unicode as raw byte escape sequences.

    When importing sanitize_string() function, you can call it with ascii_only=False, which will
    utilize unicode-sensitive regexes which help to directly
    sanitize strings themselves before dumping them into json.
    """
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
