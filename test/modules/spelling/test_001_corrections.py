import os

import pytest

from pyhttpd.conf import HttpdConf


class TestSpellingCorrections:
    """Test mod_speling URL correction behaviour.

    Ported from noe-tests ModSpelingHttpdTest.groovy.

    mod_speling fixes URL typos:
      - CheckSpelling On/Off enables or disables the module.
      - CheckCaseOnly On/Off restricts corrections to case differences only.
    Single-match corrections produce 301; multiple matches produce 300.
    """

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        if not env.has_shared_module("speling"):
            pytest.skip("mod_speling not available")
        # Create a test file in the document root that mod_speling can match.
        doc_dir = os.path.join(env.server_dir, "htdocs", "test1")
        os.makedirs(doc_dir, exist_ok=True)
        with open(os.path.join(doc_dir, "index.html"), "w") as f:
            f.write("<html><body>index</body></html>\n")

    def _configure(self, env, check_spelling, check_case_only):
        """Write an httpd config with the given mod_speling directives."""
        conf = HttpdConf(env, extras={
            f"test1.{env.http_tld}": f"""
            CheckSpelling {check_spelling}
            CheckCaseOnly {check_case_only}
            """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    # Parameterized test cases from ModSpelingHttpdTest.groovy:
    #
    # (check_case_only, check_spelling, path, expected_status)
    #
    # 404 = module disabled or correction rejected
    # 301 = single-match redirect
    @pytest.mark.parametrize("check_case_only, check_spelling, path, expected_status", [
        # Module disabled: no corrections at all
        ("Off", "Off", "/INDEX.HTML", 404),
        # Case fix with CheckCaseOnly Off
        ("Off", "On",  "/INDEX.HTML", 301),
        # Case fix with CheckCaseOnly On (allowed -- it is a case-only diff)
        ("On",  "On",  "/INDEX.HTML", 301),
        # Character substitution with CheckCaseOnly Off (allowed)
        ("Off", "On",  "/indax.html", 301),
        # Character substitution with CheckCaseOnly On (rejected)
        ("On",  "On",  "/indax.html", 404),
    ])
    def test_spelling_001(self, env, check_case_only, check_spelling,
                          path, expected_status):
        self._configure(env, check_spelling, check_case_only)
        url = env.mkurl("http", "test1", path)
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == expected_status, \
            (f"CheckSpelling {check_spelling}, CheckCaseOnly {check_case_only}, "
             f"path {path}: expected {expected_status}, "
             f"got {r.response['status']}")
