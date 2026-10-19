"""Public HTTPS downloads with pinned DNS resolution and bounded redirects."""
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit, urlunsplit


class HTTPStatusError(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__('Repository returned HTTP %s.' % status)


def https_url(value):
    if not isinstance(value, str) or not 0 < len(value) <= 4096 or any(ord(c) < 33 for c in value) or '\\' in value:
        raise ValueError('Use a public HTTPS URL without spaces or credentials.')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').encode('idna').decode('ascii').lower()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Invalid HTTPS URL.') from exc
    if parts.scheme != 'https' or not host or parts.username or parts.password or parts.fragment or port not in (None, 443):
        raise ValueError('Only public HTTPS on port 443 without credentials or fragments is supported.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Local network addresses cannot host add-on repositories.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        raise ValueError('Use a public HTTPS hostname, not an IP address.')
    return urlunsplit(('https', host, parts.path or '/', parts.query, ''))


def public_addresses(host):
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError('Repository hostname could not be resolved.') from exc
    result = []
    for family, kind, protocol, canonical, address in records:
        ip = ipaddress.ip_address(address[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError('Repository resolved to a non-public network address.')
        if address[0] not in result:
            result.append(address[0])
    if not result:
        raise ValueError('Repository hostname has no public addresses.')
    return result


class PublicHTTPSFetcher:
    def __call__(self, url, limit, progress=None):
        current = https_url(url)
        deadline = time.monotonic() + 45
        for hop in range(5):
            if progress:
                progress(0, None)
            if time.monotonic() >= deadline:
                raise ValueError('Repository download exceeded its time limit.')
            parts = urlsplit(current)
            addresses = public_addresses(parts.hostname)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('Repository download exceeded its time limit.')
            context = ssl.create_default_context()
            connection = http.client.HTTPSConnection(parts.hostname, 443, timeout=15, context=context)
            try:
                # Pin the validated address; TLS still authenticates the original hostname.
                sock = socket.create_connection((addresses[0], 443), timeout=min(15, remaining))
                try:
                    connection.sock = context.wrap_socket(sock, server_hostname=parts.hostname)
                except Exception:
                    sock.close()
                    raise
                path = (parts.path or '/') + ('?' + parts.query if parts.query else '')
                connection.request('GET', path, headers={'User-Agent': 'Metin2Studio-AddonCatalog/1', 'Accept': '*/*', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise ValueError('Repository redirect has no destination.')
                    current = https_url(urljoin(current, location))
                    continue
                if response.status != 200:
                    raise HTTPStatusError(response.status)
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    raise ValueError('Repository response must use identity encoding.')
                length = response.getheader('Content-Length')
                if length is not None and (not length.isdigit() or int(length) > limit):
                    raise ValueError('Repository response exceeds its size limit.')
                chunks, count = [], 0
                total = int(length) if length is not None else None
                if progress:
                    progress(0, total)
                while True:
                    if time.monotonic() > deadline:
                        raise ValueError('Repository download exceeded its time limit.')
                    if connection.sock is not None:
                        connection.sock.settimeout(min(15, max(0.001, deadline - time.monotonic())))
                    chunk = response.read(min(65536, limit + 1 - count))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    count += len(chunk)
                    if progress:
                        progress(count, total)
                    if count > limit:
                        raise ValueError('Repository response exceeds its size limit.')
                if length is not None and count != int(length):
                    raise ValueError('Repository download was incomplete.')
                return b''.join(chunks)
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise ValueError('HTTPS repository download failed. Check connectivity and certificate trust.') from exc
            finally:
                connection.close()
        raise ValueError('Repository returned too many redirects.')
