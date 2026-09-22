"""Resolve a client IP only across explicitly trusted proxy hops."""
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request

from .config import get_settings
from .supabase_client import get_supabase_admin_client


def client_ip(peer: str, forwarded: str | None, trusted_cidrs: tuple[str, ...]) -> str:
  trusted = tuple(ip_network(cidr) for cidr in trusted_cidrs)
  address = ip_address(peer)
  def is_trusted(value):
    return any(value in network for network in trusted)
  # A direct caller cannot influence identity with any forwarding header.
  if not is_trusted(address):
    return str(address)
  if not forwarded or len(forwarded) > 2048:
    raise ValueError('Trusted proxy did not provide a bounded client IP chain.')
  hops = forwarded.split(',')
  if len(hops) > 16:
    raise ValueError('Too many forwarding hops.')
  for hop in reversed(hops):
    address = ip_address(hop.strip())
    if not is_trusted(address):
      return str(address)
  raise ValueError('Forwarding chain has no untrusted client address.')


def enforce_us_ip(request: Request) -> None:
  settings = get_settings()
  if not settings.us_ip_beta_enabled:
    return
  try:
    if request.client is None:
      raise ValueError('Missing transport peer.')
    headers = request.headers.getlist('x-forwarded-for')
    if len(headers) > 1:
      raise ValueError('Ambiguous forwarding headers.')
    address = client_ip(request.client.host, headers[0] if headers else None,
                        settings.trusted_proxy_cidrs)
  except ValueError as error:
    raise HTTPException(status_code=403, detail='Unable to verify your network location for the US-IP beta.') from error
  try:
    allowed = get_supabase_admin_client().rpc('is_us_beta_ip', {'p_ip': address}).execute().data
  except Exception as error:
    raise HTTPException(status_code=503, detail='Network location verification is temporarily unavailable. Try again later.') from error
  if allowed is not True:
    raise HTTPException(status_code=403, detail='This beta accepts new uploads from US IP addresses. VPNs and proxies can affect location detection; IP location does not establish residency.')
