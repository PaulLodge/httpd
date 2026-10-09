import os
import shutil

import pytest

from pyhttpd.conf import HttpdConf


class TestDavOperations:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        dav_dir = os.path.join(env.gen_dir, 'dav-ops')
        if os.path.exists(dav_dir):
            shutil.rmtree(dav_dir)
        os.makedirs(dav_dir, exist_ok=True)
        import glob
        for f in glob.glob(os.path.join(env.gen_dir, 'davlock-ops*')):
            os.remove(f)
        with open(os.path.join(dav_dir, 'hello.txt'), 'w') as fd:
            fd.write('hello')
        dav_dir_conf = dav_dir.replace('\\', '/')
        lock_db_conf = os.path.join(env.gen_dir, 'davlock-ops').replace('\\', '/')
        conf = HttpdConf(env, extras={
            'base': f"""
        DavLockDB "{lock_db_conf}"
        """,
            f"test1.{env.http_tld}": f"""
        Alias /dav-ops "{dav_dir_conf}"
        <Directory "{dav_dir_conf}">
            Dav On
            Require all granted
        </Directory>
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def _dav_url(self, env, path=''):
        return env.mkurl("http", "test1", f"/dav-ops/{path}")

    def _write_dav_file(self, env, name, content):
        """Write a file directly into the DAV directory on disk."""
        dav_dir = os.path.join(env.gen_dir, 'dav-ops')
        fpath = os.path.join(dav_dir, name)
        with open(fpath, 'w') as fd:
            fd.write(content)

    def _remove_dav_file(self, env, name):
        """Remove a file from the DAV directory if it exists."""
        fpath = os.path.join(env.gen_dir, 'dav-ops', name)
        if os.path.isfile(fpath):
            os.remove(fpath)

    def _write_temp(self, env, name, content):
        """Write a temporary file outside the DAV directory for uploads."""
        fpath = os.path.join(env.gen_dir, name)
        with open(fpath, 'w') as fd:
            fd.write(content)
        return fpath

    @staticmethod
    def _lock_body():
        return ('<?xml version="1.0" encoding="utf-8"?>'
                '<D:lockinfo xmlns:D="DAV:">'
                '<D:lockscope><D:exclusive/></D:lockscope>'
                '<D:locktype><D:write/></D:locktype>'
                '<D:owner><D:href>test-owner</D:href></D:owner>'
                '</D:lockinfo>')

    def _check_response(self, r, expected, msg=""):
        assert r.response is not None, \
            f"No HTTP response (curl exit_code={r.exit_code}, " \
            f"stderr={r.stderr}): {msg}"
        assert r.response["status"] == expected, \
            f"Expected {expected}, got {r.response['status']}: {msg}"

    # HEAD request on a DAV resource returns 200
    def test_dav_002_01(self, env):
        self._write_dav_file(env, 'hello.txt', 'hello')
        url = self._dav_url(env, 'hello.txt')
        r = env.curl_raw(url, options=['-I'])
        self._check_response(r, 200, "HEAD hello.txt")

    # GET retrieves the correct file content
    def test_dav_002_02(self, env):
        self._write_dav_file(env, 'hello.txt', 'hello')
        url = self._dav_url(env, 'hello.txt')
        r = env.curl_raw(url)
        self._check_response(r, 200, "GET hello.txt")
        assert r.stdout.strip() == 'hello'

    # PUT uploads content, subsequent GET returns the same content
    def test_dav_002_03(self, env):
        self._remove_dav_file(env, 'put_test.txt')
        content = 'uploaded via put'
        fpath = self._write_temp(env, 'put_content.txt', content)
        url = self._dav_url(env, 'put_test.txt')
        r = env.curl_raw(url, options=['-T', fpath])
        self._check_response(r, 201, "PUT put_test.txt")
        # verify with GET
        r = env.curl_raw(url)
        self._check_response(r, 200, "GET put_test.txt")
        assert r.stdout.strip() == content

    # COPY duplicates a file; the copy has the original content
    def test_dav_002_04(self, env):
        self._write_dav_file(env, 'hello.txt', 'hello')
        self._remove_dav_file(env, 'hello_copy.txt')
        src_url = self._dav_url(env, 'hello.txt')
        dest_url = self._dav_url(env, 'hello_copy.txt')
        r = env.curl_raw(src_url, options=[
            '-X', 'COPY',
            '-H', f'Destination: {dest_url}'])
        self._check_response(r, 201, "COPY hello.txt")
        # verify the copy has the original content
        r = env.curl_raw(dest_url)
        self._check_response(r, 200, "GET hello_copy.txt")
        assert r.stdout.strip() == 'hello'

    # MOVE transfers a file; the source returns 404 afterwards
    def test_dav_002_05(self, env):
        self._write_dav_file(env, 'move_src.txt', 'move me')
        self._remove_dav_file(env, 'move_dest.txt')
        src_url = self._dav_url(env, 'move_src.txt')
        dest_url = self._dav_url(env, 'move_dest.txt')
        r = env.curl_raw(src_url, options=[
            '-X', 'MOVE',
            '-H', f'Destination: {dest_url}'])
        self._check_response(r, 201, "MOVE move_src.txt")
        # source should be gone
        r = env.curl_raw(src_url)
        self._check_response(r, 404, "GET move_src.txt after MOVE")
        # destination should have the content
        r = env.curl_raw(dest_url)
        self._check_response(r, 200, "GET move_dest.txt")
        assert r.stdout.strip() == 'move me'

    # DELETE removes a file; subsequent GET returns 404
    def test_dav_002_06(self, env):
        self._write_dav_file(env, 'delete_me.txt', 'delete this')
        url = self._dav_url(env, 'delete_me.txt')
        r = env.curl_raw(url, options=['-X', 'DELETE'])
        self._check_response(r, 204, "DELETE delete_me.txt")
        # verify the file is gone
        r = env.curl_raw(url)
        self._check_response(r, 404, "GET delete_me.txt after DELETE")

    # PROPFIND with Depth:1 returns a listing that includes file names
    def test_dav_002_07(self, env):
        self._write_dav_file(env, 'hello.txt', 'hello')
        url = self._dav_url(env)
        r = env.curl_raw(url, options=[
            '-X', 'PROPFIND',
            '-H', 'Depth: 1'])
        self._check_response(r, 207, "PROPFIND Depth:1")
        assert 'hello.txt' in r.stdout

    # MKCOL creates a collection; PROPFIND on the parent shows it
    def test_dav_002_08(self, env):
        col_dir = os.path.join(env.gen_dir, 'dav-ops', 'newcol')
        shutil.rmtree(col_dir, ignore_errors=True)
        url = self._dav_url(env, 'newcol')
        r = env.curl_raw(url, options=['-X', 'MKCOL'])
        self._check_response(r, 201, "MKCOL newcol")
        # verify the collection appears in the parent listing
        parent_url = self._dav_url(env)
        r = env.curl_raw(parent_url, options=[
            '-X', 'PROPFIND',
            '-H', 'Depth: 1'])
        self._check_response(r, 207, "PROPFIND after MKCOL")
        assert 'newcol' in r.stdout

    # After LOCK, PUT/DELETE/MOVE fail with 423 Locked but GET still works
    def test_dav_002_09(self, env):
        self._write_dav_file(env, 'lock_test.txt', 'lock me')
        url = self._dav_url(env, 'lock_test.txt')
        fpath = self._write_temp(env, 'lock_body.xml', self._lock_body())
        r = env.curl_raw(url, options=[
            '-X', 'LOCK',
            '-H', 'Content-Type: text/xml',
            '--data-binary', f'@{fpath}'])
        self._check_response(r, 200, "LOCK lock_test.txt")
        # PUT should fail with 423
        put_fpath = self._write_temp(env, 'put_locked.txt', 'overwrite attempt')
        r = env.curl_raw(url, options=['-T', put_fpath])
        self._check_response(r, 423, "PUT on locked resource")
        # DELETE should fail with 423
        r = env.curl_raw(url, options=['-X', 'DELETE'])
        self._check_response(r, 423, "DELETE on locked resource")
        # MOVE should fail with 423
        move_dest = self._dav_url(env, 'lock_moved.txt')
        r = env.curl_raw(url, options=[
            '-X', 'MOVE',
            '-H', f'Destination: {move_dest}'])
        self._check_response(r, 423, "MOVE on locked resource")
        # GET should still succeed on a write-locked resource
        r = env.curl_raw(url)
        self._check_response(r, 200, "GET on locked resource")
        assert r.stdout.strip() == 'lock me'
        env.httpd_error_log.ignore_recent(
            matches=[r'.*dav:error.*'])

    # After LOCK then UNLOCK, DELETE succeeds
    def test_dav_002_10(self, env):
        self._write_dav_file(env, 'unlock_test.txt', 'unlock me')
        url = self._dav_url(env, 'unlock_test.txt')
        fpath = self._write_temp(env, 'unlock_body.xml', self._lock_body())
        r = env.curl_raw(url, options=[
            '-X', 'LOCK',
            '-H', 'Content-Type: text/xml',
            '--data-binary', f'@{fpath}'])
        self._check_response(r, 200, "LOCK unlock_test.txt")
        # extract the lock token from the response header
        lock_token = r.response["header"]["lock-token"]
        # unlock the resource
        r = env.curl_raw(url, options=[
            '-X', 'UNLOCK',
            '-H', f'Lock-Token: {lock_token}'])
        self._check_response(r, 204, "UNLOCK unlock_test.txt")
        # DELETE should now succeed
        r = env.curl_raw(url, options=['-X', 'DELETE'])
        self._check_response(r, 204, "DELETE after UNLOCK")
