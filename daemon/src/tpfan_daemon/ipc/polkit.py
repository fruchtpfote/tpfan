from __future__ import annotations


class PolkitError(Exception):
    pass


def authorize(bus, sender: str, action: str) -> None:
    """Synchroner PolicyKit-CheckAuthorization."""
    proxy = bus.get_proxy(
        "org.freedesktop.PolicyKit1",
        "/org/freedesktop/PolicyKit1/Authority",
        "org.freedesktop.PolicyKit1.Authority",
    )
    subject = (
        "system-bus-name",
        {"name": ("s", sender)},
    )
    is_auth, _challenge, _details = proxy.CheckAuthorization(
        subject, action, {}, 1, ""
    )
    if not is_auth:
        raise PolkitError(f"polkit denied: {action}")
