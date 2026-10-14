import base64
import re

import pytest

from pyhttpd.conf import HttpdConf
from pyhttpd.depends import needs_dependency

from .env import SessionTestEnv


@needs_dependency("mod_session_crypto",
                  SessionTestEnv.has_shared_module("session_crypto"),
                  reason="mod_session_crypto not available")
class TestSessionCrypto:
    """Verify that mod_session_crypto authenticates encrypted session
    cookies so that forged cookies with manipulated padding are
    rejected."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env, extras={
            'base': [
                "LogLevel debug",
                "Session On",
                "SessionEnv On",
                "SessionCookieName session path=/",
                "SessionHeader X-Replace-Session",
                "SessionCryptoPassphrase PavelIsTheVeryBest",
            ],
        })
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0

    def _oracle(self, env, cookie_value):
        """Send a session cookie and return whether the server passed
        decrypted data through to the CGI script (True) or rejected it
        (False)."""
        url = env.mkurl("http", "cgi", "/session_crypto.py")
        r = env.curl_get(url, options=[
            "-b", f"session={cookie_value}",
        ])
        assert r.exit_code == 0, r.stderr
        assert r.response["status"] == 200
        body = r.response["body"].decode()
        return "OMG, OMG I got cookie! motto=This+is+the+end" in body

    def _forge(self, env, orig_data, block_size=16):
        """Attempt a padding oracle attack by inserting a block of null
        bytes at the penultimate position and sweeping through all 256
        possible values for the last byte of that block.

        Returns True if any forged cookie was accepted (meaning the
        server is vulnerable), False otherwise."""
        decoded = base64.b64decode(orig_data)

        # Build an extended buffer with an extra null block inserted
        # before the last block.
        prefix = decoded[:-block_size]
        last_block = decoded[-block_size:]
        extended = bytearray(prefix) + bytearray(block_size) + bytearray(last_block)

        for v in range(256):
            # Set the last byte of the inserted (penultimate) block.
            extended[-(block_size + 1)] = v
            forged_cookie = base64.b64encode(bytes(extended)).decode()
            if self._oracle(env, forged_cookie):
                return True
        return False

    def test_session_003_01_forged_padding_rejected(self, env):
        """Forged session cookies with manipulated padding must be
        rejected by mod_session_crypto."""
        # First request: let the server create an encrypted session
        # cookie.  The CGI script emits X-Replace-Session to populate
        # the session, and mod_session_crypto encrypts it into the
        # Set-Cookie header.
        url = env.mkurl("http", "cgi", "/session_crypto.py")
        r = env.curl_get(url, options=["-c", "-"])
        assert r.exit_code == 0, r.stderr
        assert r.response["status"] == 200

        # Extract the session cookie value from the Set-Cookie header.
        set_cookie = r.response["header"].get("set-cookie", "")
        m = re.match(r'session=([^;]+)', set_cookie)
        assert m, f"Expected a 'session' Set-Cookie header, got: {set_cookie!r}"
        session_value = m.group(1)
        assert session_value, "Session cookie value must not be empty"

        # Verify the legitimate cookie is accepted before testing
        # forgery, so we know the oracle works.
        assert self._oracle(env, session_value), \
            "The original encrypted cookie should be accepted"

        # Attempt the padding oracle attack: all 256 forged values
        # must be rejected.
        assert not self._forge(env, session_value), \
            "Forged session cookies must not be accepted by the server"

        # The debug-level session_crypto log messages are expected.
        env.httpd_error_log.ignore_recent(
            matches=[r".*session_crypto.*"])
