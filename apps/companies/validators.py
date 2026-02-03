"""
Free email domain blocklist and company email validation utilities.
"""

FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "mail.com",
    "protonmail.com",
    "zoho.com",
    "yandex.com",
    "gmx.com",
    "live.com",
    "me.com",
    "msn.com",
    "inbox.com",
    "fastmail.com",
    "tutanota.com",
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.com",
})


def extract_email_domain(email: str) -> str:
    """Extract the domain part from an email address."""
    return email.strip().lower().rsplit("@", 1)[-1]


def is_free_email(email: str) -> bool:
    """Return True if the email belongs to a free email provider."""
    domain = extract_email_domain(email)
    return domain in FREE_EMAIL_DOMAINS
