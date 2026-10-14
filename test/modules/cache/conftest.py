import logging
import os
import sys

import pytest

from .env import CacheTestEnv

sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))


def pytest_report_header(config, start_path):
    env = CacheTestEnv()
    return f"cache [apache: {env.get_httpd_version()}, mpm: {env.mpm_module}, {env.prefix}]"


@pytest.fixture(scope="package")
def env(pytestconfig) -> CacheTestEnv:
    logging.getLogger('').setLevel(level=logging.INFO)
    env = CacheTestEnv(pytestconfig=pytestconfig)
    env.setup_httpd()
    env.apache_access_log_clear()
    env.httpd_error_log.clear_log()
    return env


@pytest.fixture(autouse=True, scope="package")
def _stop_package_scope(env):
    # AH01254 fires when the ScriptSock path is too long for a Unix
    # domain socket (108 bytes).  This is an infrastructure issue
    # caused by deeply nested working directories, not the tests.
    env.httpd_error_log.add_ignored_lognos(["AH01254"])
    yield
    assert env.apache_stop() == 0
