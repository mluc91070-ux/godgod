"""OAuth 1.0a request signing.

Posting to X needs *user* context. An app-only bearer token can read and cannot
write, which is the single most expensive thing to discover late: a project can
have a working bearer token, a paid tier, and still be unable to publish.

Signing is about sixty lines of standard library, so this is written out rather
than pulling in a dependency for it. RFC 5849, HMAC-SHA1.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode


def _quote(value: str) -> str:
    """Percent-encoding per RFC 5849 §3.6: unreserved characters are exactly
    ALPHA / DIGIT / '-' / '.' / '_' / '~', and everything else is escaped."""
    return quote(str(value), safe="-._~")


@dataclass(frozen=True)
class OAuth1Credentials:
    """The four values X calls consumer key/secret and access token/secret."""

    consumer_key: str
    consumer_secret: str
    access_token: str
    access_token_secret: str

    @property
    def complete(self) -> bool:
        return all(
            (
                self.consumer_key,
                self.consumer_secret,
                self.access_token,
                self.access_token_secret,
            )
        )


def signature_base(method: str, url: str, params: dict[str, str]) -> str:
    """The string that gets signed: method, url and parameters, each encoded
    once and then the whole joined and encoded again."""
    encoded = sorted((_quote(k), _quote(v)) for k, v in params.items())
    joined = "&".join(f"{k}={v}" for k, v in encoded)
    return "&".join([method.upper(), _quote(url), _quote(joined)])


def sign(
    credentials: OAuth1Credentials,
    method: str,
    url: str,
    *,
    query: dict[str, str] | None = None,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Build the `Authorization: OAuth ...` header for one request.

    A JSON body is not part of the signature base — only the query string is —
    which is why the body is absent from `params` here.
    """
    oauth_params = {
        "oauth_consumer_key": credentials.consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": credentials.access_token,
        "oauth_version": "1.0",
    }

    base = signature_base(method, url, {**oauth_params, **(query or {})})
    key = f"{_quote(credentials.consumer_secret)}&{_quote(credentials.access_token_secret)}"
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    signed = {**oauth_params, "oauth_signature": base64.b64encode(digest).decode()}

    return "OAuth " + ", ".join(
        f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(signed.items())
    )


def urlencode_rfc5849(params: dict[str, str]) -> str:
    return urlencode(params, quote_via=_quote)
