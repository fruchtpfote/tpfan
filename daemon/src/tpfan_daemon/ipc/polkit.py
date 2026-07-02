from __future__ import annotations


class PolkitError(Exception):
    pass


def authorize(bus, sender: str, action: str) -> None:
    """PolicyKit-CheckAuthorization. Fail-closed bei Bus-Fehlern.

    Der CheckAuthorization-Call läuft **asynchron**; währenddessen wird der
    Default-GLib-Main-Context über eine verschachtelte MainLoop weitergepumpt.
    Dadurch feuert der Daemon-Tick — und damit das systemd-Watchdog-Heartbeat —
    weiter, auch während ein interaktiver polkit-Auth-Dialog offen ist.

    Ein synchroner Call würde den Main-Thread blockieren; überschreitet der
    Dialog dann WatchdogSec, killt systemd den Daemon per SIGABRT (die GUI
    zeigt dann 'Remote peer disconnected').
    """
    try:
        from gi.repository import GLib
        proxy = bus.get_proxy(
            "org.freedesktop.PolicyKit1",
            "/org/freedesktop/PolicyKit1/Authority",
            "org.freedesktop.PolicyKit1.Authority",
        )
        subject = (
            "system-bus-name",
            {"name": GLib.Variant("s", sender)},
        )
        loop = GLib.MainLoop()
        state: dict = {}

        def _on_reply(call):
            try:
                state["result"] = call()
            except Exception as e:  # noqa: BLE001 — an outer handler fail-closed
                state["error"] = e
            finally:
                if loop.is_running():
                    loop.quit()

        # flags=1 == AllowUserInteraction (interaktiver Auth-Dialog erlaubt).
        proxy.CheckAuthorization(
            subject, action, {}, 1, "", callback=_on_reply
        )
        # Die Antwort kommt erst beim Iterieren des Main-Context. Nur blockieren,
        # wenn sie nicht bereits synchron geliefert wurde.
        if "result" not in state and "error" not in state:
            loop.run()

        if "error" in state:
            raise state["error"]
        is_auth, _challenge, _details = state["result"]
    except PolkitError:
        raise
    except Exception as e:
        raise PolkitError(f"polkit authority unavailable: {e}") from e
    if not is_auth:
        raise PolkitError(f"polkit denied: {action}")
