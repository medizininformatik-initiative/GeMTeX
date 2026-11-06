"""Display names for policy identifiers; serialized values remain unchanged."""


def policy_label(list_type: str) -> str:
    return {"whitelist": "inclusion list", "blacklist": "exclusion list"}.get(list_type, list_type)


def finding_reason_label(reason: str) -> str:
    return {
        "not_in_whitelist": "not on inclusion list",
        "blacklisted": "on exclusion list",
    }.get(reason, reason)


def suggestion_status_label(status: str) -> str:
    # Other status identifiers retain their established report display.
    return {"blacklisted_no_auto_sanitization": "excluded_no_auto_sanitization"}.get(status, status)
