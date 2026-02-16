"""
Functions for best-effort redaction of personal sensitive information from submitted logs.
"""

import logging

import regex as re

from sanitization_regexes import (
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
    FALSE_POSITIVES_PARENTHESISED_NAMES,
    CRLF_NEWLINE_ESCAPED,
    CR_ESCAPED,
    CRLF_NEWLINE,
    CR_NEWLINE,
)

from resources import (
    GlobalAuditor,
    RedactionPipelineStep,
)

from utils import skip_false_positives, skip_false_positives_escaped

logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class RedactionPipeline:
    """
    A list of RedactionPipelineSteps that are used during sanitization.
    Choose correct regexes and auditing options.
    """

    # pylint: disable=too-many-locals
    def __init__(self, escaped: bool, audit: GlobalAuditor | None):
        crlf_newlines = RedactionPipelineStep(
            pattern=CRLF_NEWLINE_ESCAPED if escaped else CRLF_NEWLINE,
            replacement="\\n" if escaped else "\n",
            auditing={},
        )
        cr_newlines = RedactionPipelineStep(
            pattern=CR_ESCAPED if escaped else CR_NEWLINE,
            replacement="\\n" if escaped else "\n",
            auditing={},
        )
        date_fullname_email = RedactionPipelineStep(
            pattern=(
                HEADER_DATE_FULLNAME_EMAIL_REGEX
                if escaped
                else UNICODE_HEADER_DATE_FULLNAME_EMAIL_REGEX
            ),
            replacement=rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"name": audit.date_fullnames, "email": audit.emails}
            if audit
            else {},
        )
        date_nickname_email = RedactionPipelineStep(
            pattern=HEADER_DATE_NICKNAME_EMAIL_REGEX,
            replacement=rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"nick": audit.nicknames, "email": audit.emails} if audit else {},
        )
        fullname_parentheses = RedactionPipelineStep(
            pattern=(
                FULLNAME_IN_PARENTHESES_REGEX
                if escaped
                else UNICODE_FULLNAME_IN_PARENTHESES_REGEX
            ),
            replacement=skip_false_positives_escaped
            if escaped
            else skip_false_positives,
            auditing={"pname": audit.parenthesised_names} if audit else {},
        )
        author_fullname_email = RedactionPipelineStep(
            pattern=AUTHOR_FULLNAME_REGEX if escaped else UNICODE_AUTHOR_FULLNAME_REGEX,
            replacement=f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"name": audit.fullnames, "email": audit.emails} if audit else {},
        )
        author_nickname_email = RedactionPipelineStep(
            pattern=AUTHOR_NICKNAME_REGEX,
            replacement=f"Author: {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"nick": audit.nicknames, "email": audit.emails} if audit else {},
        )
        date_email = RedactionPipelineStep(
            pattern=HEADER_DATE_EMAIL_REGEX,
            replacement=rf"\g<year> {NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"email": audit.emails, "emailnb": audit.emails} if audit else {},
        )
        fullname_email = RedactionPipelineStep(
            pattern=HEADER_FULLNAME_EMAIL_REGEX
            if escaped
            else UNICODE_HEADER_FULLNAME_EMAIL_REGEX,
            replacement=f"{NAME_PLACEHOLDER} <{EMAIL_PLACEHOLDER}>",
            auditing={"name": audit.fullnames, "email": audit.emails} if audit else {},
        )
        only_email = RedactionPipelineStep(
            pattern=EMAIL_REGEX,
            replacement=f"<{EMAIL_PLACEHOLDER}>",
            auditing={"email": audit.emails} if audit else {},
        )
        rsa_key = RedactionPipelineStep(
            pattern=RSA_KEY_REGEX,
            replacement=f"RSA key {'FFFF' * 10}",
            auditing={"rsa": audit.rsa_keys} if audit else {},
        )
        pubkey = RedactionPipelineStep(
            pattern=PUBKEY_REGEX,
            replacement=f"pubkey-{'ffff' * 10}",
            auditing={"pubkey": audit.pubkeys} if audit else {},
        )
        gpg_fingerprint = RedactionPipelineStep(
            pattern=GPG_FINGERPRINT_REGEX,
            replacement=f"Fingerprint:{' FFFF' * 10}",
            auditing={"fingerprint": audit.gpg_fingerprints} if audit else {},
        )
        # NOTE: If needed, here we can expand the pipeline with redacting
        # other types of data, such as IP addresses, UUIDs, etc.

        # In the steps before we replaced names and emails with strings that don't match other
        # redaction steps, so we wouldn't be overwriting these matches,
        # now we replace them with actual "placeholders".
        # These two steps should be last (or at least after any name/email redactions).
        final_name_correction = RedactionPipelineStep(
            pattern=NAME_PLACEHOLDER_REGEX, replacement=NAME_CONTACT, auditing={}
        )
        final_email_correction = RedactionPipelineStep(
            pattern=EMAIL_PLACEHOLDER_REGEX, replacement=EMAIL_CONTACT, auditing={}
        )
        self.steps = [
            crlf_newlines,
            cr_newlines,
            date_fullname_email,
            date_nickname_email,
            fullname_parentheses,
            author_fullname_email,
            author_nickname_email,
            date_email,
            fullname_email,
            only_email,
            rsa_key,
            pubkey,
            gpg_fingerprint,
            final_name_correction,
            final_email_correction,
        ]


def redaction_ignore_indexes(
    log: str, redaction: RedactionPipelineStep, file_path: str
) -> str:
    """
    Redacting used for non-json (or broken) files, here we ignore index corrections/adjustments.
    This version reads the whole json as raw text file (unescaped sequences, etc).
    """
    # We go in reverse, because if we change something at the start, not only are all snippets
    # AFTER affected, but also the match indexes are now all wrong. We would have to have some
    # sort of an overall delta-correction variable, which we would need to factor into the match
    # start/end indexes. Going in reverse means only updating the snippets while not disrupting
    # match indexes, which is more elegant.
    matches = list(redaction.pattern.finditer(log))
    for match in reversed(matches):
        start_pos, end_pos = match.span()
        replacement = (
            redaction.replacement(match)
            if callable(redaction.replacement)
            else match.expand(redaction.replacement)
        )
        log = log[:start_pos] + replacement + log[end_pos:]
        for group_name, auditor in redaction.auditing.items():
            group = match.groupdict().get(group_name)
            if group:
                # we do skip false-positive parenthesised name redaction,
                # but we also have to explicitly stop its auditing
                if (
                    group_name == "pname"
                    and group in FALSE_POSITIVES_PARENTHESISED_NAMES
                ):
                    continue
                auditor.insert(group, file_path, match.group(0))
    return log


# pylint: disable=too-many-locals
def redaction_with_index_consistency(
    log: str,
    redaction: RedactionPipelineStep,
    file_path: str,
    snippets: list[dict],
) -> str:
    """
    Redact personal information based on 'redaction' pattern and replacement,
    while also keeping start-end snippet indexes consistent with changes.
    """
    matches = list(redaction.pattern.finditer(log))

    # see redaction_ignore_indexes() why we use reversed
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
        for snip in snippets:
            start_index = snip.get("start_index")
            end_index = snip.get("end_index")
            if not (isinstance(start_index, int) and isinstance(end_index, int)):
                continue
            # if the snippets starts/ends "inside" the match, then we snap to the start/end of
            # redaction, if the snippets start/end "after" the match, we change them by delta
            if start_index >= end_pos:
                snip["start_index"] += delta
            elif start_pos < start_index < end_pos:
                snip["start_index"] = start_pos

            if end_index >= end_pos:
                snip["end_index"] += delta
            elif start_pos < end_index < end_pos:
                snip["end_index"] = start_pos + len(replacement)

        # NOTE: this would be much better and generalized auditing process
        for group_name, auditor in redaction.auditing.items():
            group = match.groupdict().get(group_name)
            if group:
                if (
                    group_name == "pname"
                    and group in FALSE_POSITIVES_PARENTHESISED_NAMES
                ):
                    continue
                auditor.insert(group, file_path, match.group(0))
    return log


def sanitize_string(
    value: str,
    file_path: str,
    snippets: list,
    escaped: bool = False,
    audit: GlobalAuditor | None = None,
) -> str:
    """Run the whole personal data redaction pipeline."""
    if not isinstance(value, str):
        return value

    pipeline = RedactionPipeline(escaped, audit)
    for step in pipeline.steps:
        if escaped:
            value = redaction_ignore_indexes(value, step, file_path)
        else:
            value = redaction_with_index_consistency(value, step, file_path, snippets)

    return value


def remove_fas_username(json_root_object: dict) -> None:
    """Expects username in the top-level of the dict"""
    if "username" in json_root_object:
        json_root_object["username"] = None


def try_sanitizing_field(
    json_obj: dict, field: str, path: str, audit: GlobalAuditor | None
):
    """
    Either sanitize a string or handle it like a snippet. In some cases, even
    `how_to_fix` or `fail_reason` can have text/comments embedded inside,
    instead of directly being a string = probably an older schema.
    """
    dict_entry = json_obj.get(field)
    if isinstance(dict_entry, str):
        json_obj[field] = sanitize_string(
            dict_entry, path, [], escaped=False, audit=audit
        )
    elif isinstance(dict_entry, dict):
        try_sanitizing_field(dict_entry, "text", path, audit)
        try_sanitizing_field(dict_entry, "comment", path, audit)
        try_sanitizing_field(dict_entry, "user_comment", path, audit)


def sanitize_log_schema(
    log_obj: dict, file_path: str, audit: GlobalAuditor | None
) -> None:
    """
    Run redaction pipelines for embedded log objects, following the expected schema:
    `obj.content` = log content as a string
    `obj.snippets` = list of snippets (with redactable `text`, `comment/user_comment` fields)
    """
    log = log_obj.get("content")
    snippets = log_obj.get("snippets", [])
    if not isinstance(log, str):
        return
    log_obj["content"] = sanitize_string(
        log, file_path, snippets, escaped=False, audit=audit
    )
    for s in snippets:
        if not isinstance(s, dict):
            continue
        try_sanitizing_field(s, "user_comment", file_path, audit=audit)
        try_sanitizing_field(s, "comment", file_path, audit=audit)
        try_sanitizing_field(s, "text", file_path, audit=audit)


def sanitize_json_file(
    json_obj: dict, file_path: str, audit: GlobalAuditor | None
) -> dict:
    """
    Redact all personal data from a json object's string fields, following an expected schema.

    We redact `fail_reason`, `how_to_fix`, `spec_file.content`, `container_file.content`.
    Then we do redact logfiles and adjust their corresponding snippets
    according to the expected schema `.logs.logfile.content` and `.logs.logfile.snippets`.
    Within snippets, we also redact `snippet.text` and `snippet.comment`.
    """
    remove_fas_username(json_obj)
    try_sanitizing_field(json_obj, "fail_reason", file_path, audit)
    try_sanitizing_field(json_obj, "how_to_fix", file_path, audit)
    specfile = json_obj.get("spec_file")
    if specfile:
        sanitize_log_schema(specfile, file_path, audit)
    containerfile = json_obj.get("container_file")
    if containerfile:
        sanitize_log_schema(containerfile, file_path, audit)
    log_dict = json_obj.get("logs")
    if isinstance(log_dict, dict):
        for log_data in log_dict.values():
            if isinstance(log_data, dict):
                sanitize_log_schema(log_data, file_path, audit)
    return json_obj


def sanitize_normal_file_raw(
    file_path: str, audit: GlobalAuditor | None = None
) -> None:
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
        for line in content:
            if re.match(USERNAME_REGEX, line):
                redacted_username = USERNAME_REGEX.sub(username_placeholder, line)
                redacted_content.append(redacted_username)
                continue
            # Since we don't call sanitize_string after json.load(), we can assume
            # that the escaped sequences have not been automatically converted to characters,
            # thus we pass escaped=True
            redacted_content.append(
                sanitize_string(line, file_path, [], escaped=True, audit=audit)
            )
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("".join(redacted_content))
        f.write("\n")
