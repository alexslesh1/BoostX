"""Pure packet-field mutation for the NETWORK-layer TCP interceptor,
isolated from WinDivert I/O (open/recv/send) so it can be unit tested
against real `pydivert.Packet` objects without ever opening a WinDivert
handle or needing a Windows driver.

Rewrites only the destination — never the source or the outbound
interface — because WinDivert's own documentation states the interface
fields are ignored for *outbound* re-injection; the only field this
codebase can reliably use to move a tracked packet off its
already-decided path is where it's addressed to. Redirecting to a
loopback address is WinDivert's own documented pattern for this exact
"send matching traffic to a local proxy" use case (see the bundled
`streamdump` example) — the interface question doesn't arise here because
loopback delivery isn't routed by interface the way real inter-host
traffic is.
"""
from __future__ import annotations

_LOCALHOST = "127.0.0.1"


def redirect_to_local_relay(packet, relay_port: int) -> None:
    packet.dst_addr = _LOCALHOST
    packet.dst_port = relay_port
    packet.is_loopback = True
    packet.recalculate_checksums()
