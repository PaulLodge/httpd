"""Concurrent digest authentication must not allow cross-user access.

When multiple clients authenticate concurrently against a threaded MPM,
a race condition must not allow one user to gain access by presenting
credentials computed for a different user. Specifically, a request which
carries a valid digest response computed for user A but claims to be
user B (the "impostor") must always be rejected, regardless of timing.

The test spawns parallel threads: "good" threads perform normal digest
authentication, while "bad" threads compute the digest with the correct
user's credentials but substitute a different username in the header.
The bad threads must never receive a 200 response.
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from . import digest_client as dc
from .env import AAATestEnv


class TestDigestConcurrent:

    ITERATIONS = 200

    def url(self, env, path="secret.txt"):
        return env.mkurl("http", "aaa", "/digest/default/" + path)

    def uri(self):
        return "/digest/default/secret.txt"

    def challenge(self, env):
        r = env.curl_get(self.url(env))
        assert r.response["status"] == 401
        return dc.DigestChallenge.parse(r.response["header"]["www-authenticate"])

    def _good_attempt(self, env):
        """Perform a legitimate digest authentication cycle."""
        challenge = self.challenge(env)
        auth = dc.build_authorization(
            AAATestEnv.DIGEST_USER, challenge, AAATestEnv.DIGEST_PASSWORD,
            method="GET", uri=self.uri())
        r = env.curl_get(self.url(env),
                         options=["-H", f"Authorization: {auth}"])
        return r.response["status"]

    def _bad_attempt(self, env):
        """Attempt to authenticate as DIGEST_USER2 using DIGEST_USER's
        credentials. This computes a valid digest response for
        DIGEST_USER but substitutes DIGEST_USER2 as the username in
        the Authorization header. This must always be rejected."""
        challenge = self.challenge(env)
        # Compute the digest response using DIGEST_USER's credentials
        h1 = dc.ha1(AAATestEnv.DIGEST_USER, challenge.realm,
                     AAATestEnv.DIGEST_PASSWORD)
        h2 = dc.ha2("GET", self.uri())
        nc = "00000001"
        cnonce = "impostor-cnonce"
        response_hash = dc.request_digest(
            h1, challenge.nonce, nc, cnonce, "auth", h2)
        # But claim to be DIGEST_USER2
        parts = [
            f'username="{AAATestEnv.DIGEST_USER2}"',
            f'realm="{challenge.realm}"',
            f'nonce="{challenge.nonce}"',
            f'uri="{self.uri()}"',
            f'response="{response_hash}"',
            'algorithm=MD5',
            'qop=auth',
            f'nc={nc}',
            f'cnonce="{cnonce}"',
        ]
        if challenge.opaque:
            parts.append(f'opaque="{challenge.opaque}"')
        auth = "Digest " + ", ".join(parts)
        r = env.curl_get(self.url(env),
                         options=["-H", f"Authorization: {auth}"])
        return r.response["status"]

    @pytest.mark.skipif(sys.platform == "win32",
                        reason="threading test not suited for mpm_winnt")
    def test_digest_017_01_impostor_rejected_under_concurrent_load(self, env):
        # Skip if the MPM is prefork (single-threaded workers), since the
        # race condition this tests for requires a threaded MPM.
        if env.mpm_module == "mpm_prefork":
            pytest.skip("race condition test requires a threaded MPM")

        cpus = os.cpu_count() or 2
        n_good = cpus * 2
        n_bad = cpus
        impostor_succeeded = threading.Event()
        impostor_status_codes = []
        lock = threading.Lock()

        def good_worker():
            for _ in range(self.ITERATIONS):
                if impostor_succeeded.is_set():
                    break
                self._good_attempt(env)

        def bad_worker():
            for _ in range(self.ITERATIONS):
                if impostor_succeeded.is_set():
                    break
                status = self._bad_attempt(env)
                if status == 200:
                    with lock:
                        impostor_status_codes.append(status)
                    impostor_succeeded.set()
                    break

        threads = []
        for _ in range(n_good):
            t = threading.Thread(target=good_worker)
            threads.append(t)
        for _ in range(n_bad):
            t = threading.Thread(target=bad_worker)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        env.httpd_error_log.ignore_recent(
            lognos=["AH01794", "AH01790", "AH01776", "AH01782"])

        assert not impostor_succeeded.is_set(), \
            "an impostor was able to authenticate using another user's " \
            "credentials during concurrent access"
