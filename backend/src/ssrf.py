"""Validate every address aiohttp can select for remote resources."""

import ipaddress
import socket

import aiohttp
from aiohttp.helpers import is_ip_address

from src.constants import LOGDETECTIVE_MAX_CONNECTION_LIMIT


def check_address(value: str) -> None:
    """Apply the public-only policy to literal addresses and DNS answers."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise socket.gaierror(socket.EAI_FAIL, "Invalid remote IP address") from exc
    address = getattr(address, "ipv4_mapped", None) or address
    special_use = (
        address.is_reserved
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or (isinstance(address, ipaddress.IPv6Address) and address.is_site_local)
    )
    if "%" in value or not address.is_global or address.is_multicast or special_use:
        raise socket.gaierror(
            socket.EAI_FAIL, "Remote log URL resolves to a forbidden address"
        )


class SSRFProtectedResolver(aiohttp.ThreadedResolver):
    """Return the full DNS snapshot only when all its addresses are permitted."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        answers = await super().resolve(host, port, family)
        if not answers:
            raise socket.gaierror(
                socket.EAI_FAIL, "Remote log hostname has no addresses"
            )
        for answer in answers:
            check_address(answer["host"])
        return answers


class SSRFProtectedConnector(aiohttp.TCPConnector):
    """Disable reuse and validate IP literals that bypass aiohttp's resolver."""

    def __init__(self):
        super().__init__(
            resolver=SSRFProtectedResolver(),
            force_close=True,
            use_dns_cache=False,
            limit=LOGDETECTIVE_MAX_CONNECTION_LIMIT,
        )

    async def _resolve_host(self, host, port, traces=None):
        if "%" in host or is_ip_address(host):
            check_address(host)
        return await super()._resolve_host(host, port, traces)
