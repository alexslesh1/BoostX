"""Windows-only helpers to force a socket's outbound traffic through a
specific network interface (the WireGuard TUN adapter), without touching
the system routing table — this is what makes split tunneling possible
without a default route or a packet-interception driver.

Both APIs used here (`GetIpAddrTable`, `IP_UNICAST_IF`) only exist on
Windows. This module is safe to import on any platform (no top-level
Windows-only calls), but every function raises OSError/AttributeError if
called off Windows.
"""
from __future__ import annotations

import ctypes
import socket
import struct
import sys
from ctypes import wintypes

# ws2ipdef.h: #define IP_UNICAST_IF 31. Not exposed as socket.IP_UNICAST_IF
# on non-Windows Python builds, so the numeric value is hardcoded.
_IP_UNICAST_IF = 31
_ERROR_INSUFFICIENT_BUFFER = 122


class _MibIpAddrRow(ctypes.Structure):
    _fields_ = [
        ("dwAddr", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("dwMask", wintypes.DWORD),
        ("dwBCastAddr", wintypes.DWORD),
        ("dwReasmSize", wintypes.DWORD),
        ("unused1", ctypes.c_ushort),
        ("wType", ctypes.c_ushort),
    ]


def find_interface_index_for_ip(ip_address: str) -> int | None:
    """Returns the Windows interface index whose IPv4 address matches
    `ip_address` (e.g. the WireGuard adapter's `10.8.0.X`), or None if no
    adapter currently has that address (tunnel not up yet)."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        raise OSError("find_interface_index_for_ip is only available on Windows")

    iphlpapi = ctypes.WinDLL("iphlpapi.dll")
    ws2_32 = ctypes.WinDLL("ws2_32.dll")
    ws2_32.inet_addr.restype = ctypes.c_uint32
    ws2_32.inet_addr.argtypes = [ctypes.c_char_p]

    target = ws2_32.inet_addr(ip_address.encode("ascii"))

    size = wintypes.ULONG(0)
    result = iphlpapi.GetIpAddrTable(None, ctypes.byref(size), False)
    if result != _ERROR_INSUFFICIENT_BUFFER:
        raise OSError(f"GetIpAddrTable size query failed with code {result}")

    buffer = ctypes.create_string_buffer(size.value)
    result = iphlpapi.GetIpAddrTable(buffer, ctypes.byref(size), False)
    if result != 0:
        raise OSError(f"GetIpAddrTable failed with code {result}")

    num_entries = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD))[0]
    row_offset = ctypes.sizeof(wintypes.DWORD)
    row_size = ctypes.sizeof(_MibIpAddrRow)
    for i in range(num_entries):
        row = _MibIpAddrRow.from_buffer_copy(buffer, row_offset + i * row_size)
        if row.dwAddr == target:
            return row.dwIndex
    return None


def bind_socket_to_interface(sock: socket.socket, interface_index: int) -> None:
    """Forces `sock`'s outbound packets to be sent via the given interface,
    regardless of the system routing table. IP_UNICAST_IF is unusual among
    Windows socket options in that it expects the interface index packed
    in network (big-endian) byte order, not host order."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        raise OSError("bind_socket_to_interface is only available on Windows")

    packed_index = struct.pack("!I", interface_index)
    sock.setsockopt(socket.IPPROTO_IP, _IP_UNICAST_IF, packed_index)
