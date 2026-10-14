"""Nonce invalidation across a server restart.

The nonce secret used by mod_auth_digest is regenerated on each server
start. A nonce issued before a restart must therefore be rejected
afterwards, even if it has not expired, because the server can no longer
verify it. The client should receive a stale=true challenge so it can
seamlessly re-authenticate with a fresh nonce.

This test verifies the complete sequence: authenticate, restart, confirm
the old nonce is rejected, and confirm that a new handshake succeeds.
"""

import sys

import pytest

from . import digest_client as dc
from .env import AAATestEnv


class TestDigestNonceInvalidation:

    def url(self, env, path="secret.txt"):
        return env.mkurl("http", "aaa", "/digest/default/" + path)

    def uri(self):
        return "/digest/default/secret.txt"

    def challenge(self, env):
        r = env.curl_get(self.url(env))
        assert r.response["status"] == 401
        return dc.DigestChallenge.parse(r.response["header"]["www-authenticate"])

    def authenticate(self, env, challenge, nc="00000001",
                     cnonce="nonce-invalidation-test"):
        auth = dc.build_authorization(
            AAATestEnv.DIGEST_USER, challenge, AAATestEnv.DIGEST_PASSWORD,
            method="GET", uri=self.uri(), nc=nc, cnonce=cnonce)
        return env.curl_get(self.url(env),
                            options=["-H", f"Authorization: {auth}"])

    @pytest.mark.xfail(sys.platform == "win32", reason=
                        "mpm_winnt child is a separate process, "
                        "ap_retained_data does not survive restart")
    def test_digest_016_01_nonce_rejected_after_restart(self, env):
        # 1. Obtain a challenge and authenticate successfully.
        challenge = self.challenge(env)
        r = self.authenticate(env, challenge)
        assert r.response["status"] == 200

        # 2. Restart the server so the nonce secret is regenerated.
        assert env.apache_restart() == 0

        # 3. The same authorization (same nonce) must now be rejected
        #    because the server can no longer verify the old nonce.
        r = self.authenticate(env, challenge, nc="00000002",
                              cnonce="nonce-invalidation-after-restart")
        assert r.response["status"] == 401
        env.httpd_error_log.ignore_recent(lognos=["AH01776"])

    @pytest.mark.xfail(sys.platform == "win32", reason=
                        "mpm_winnt child is a separate process, "
                        "ap_retained_data does not survive restart")
    def test_digest_016_02_fresh_nonce_works_after_restart(self, env):
        # After a restart rejects the old nonce, a fresh challenge from
        # the restarted server must allow the client to authenticate
        # again.
        challenge = self.challenge(env)
        r = self.authenticate(env, challenge)
        assert r.response["status"] == 200

        assert env.apache_restart() == 0

        # The old nonce fails.
        r = self.authenticate(env, challenge, nc="00000002",
                              cnonce="post-restart-stale")
        assert r.response["status"] == 401
        env.httpd_error_log.ignore_recent(lognos=["AH01776"])

        # A fresh challenge from the restarted server succeeds.
        fresh_challenge = self.challenge(env)
        r = self.authenticate(env, fresh_challenge,
                              cnonce="post-restart-fresh")
        assert r.response["status"] == 200
