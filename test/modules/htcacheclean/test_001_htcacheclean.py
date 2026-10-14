import os
import shutil

import pytest


class TestHtcacheclean:
    """Tests for the htcacheclean CLI tool.

    htcacheclean manages the disk cache created by mod_cache_disk.
    With the -t flag, it should delete empty directories within the
    cache root.
    """

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        htcacheclean = env.htcacheclean
        if not os.path.isfile(htcacheclean):
            pytest.skip(f"htcacheclean not found at {htcacheclean}")

    def test_htcacheclean_001_01_removes_empty_dirs(self, env):
        """htcacheclean -t removes empty subdirectories from the cache
        root."""
        cache_root = os.path.join(env.server_dir, "cache")
        empty_dir = os.path.join(cache_root, "empty", "sub", "folder")

        # Set up: create nested empty directories under the cache root
        os.makedirs(empty_dir, exist_ok=True)
        assert os.path.isdir(empty_dir), \
            "Failed to create empty cache subdirectory"

        # Run htcacheclean with -t (delete empty dirs) -p (path) -l (limit)
        r = env.run([
            env.htcacheclean,
            "-p", os.path.join(cache_root, "empty").replace("\\", "/"),
            "-t",
            "-l", "100M",
        ])
        assert r.exit_code == 0, \
            f"htcacheclean exited with code {r.exit_code}: {r.stderr}"

        # The "empty/sub" directory tree should have been cleaned up
        parent_of_sub = os.path.join(cache_root, "empty", "sub")
        assert not os.path.exists(parent_of_sub), \
            "htcacheclean -t did not remove empty cache subdirectories"

        # Clean up the cache root
        if os.path.isdir(cache_root):
            shutil.rmtree(cache_root)

    def test_htcacheclean_001_02_preserves_nonempty_dirs(self, env):
        """htcacheclean -t preserves non-empty directories."""
        cache_root = os.path.join(env.server_dir, "cache")
        sub_dir = os.path.join(cache_root, "notempty", "sub")
        os.makedirs(sub_dir, exist_ok=True)

        # Create a file so the directory is not empty
        test_file = os.path.join(sub_dir, "keep.data")
        with open(test_file, "w") as f:
            f.write("cache data placeholder\n")

        r = env.run([
            env.htcacheclean,
            "-p", os.path.join(cache_root, "notempty").replace("\\", "/"),
            "-t",
            "-l", "100M",
        ])
        assert r.exit_code == 0, \
            f"htcacheclean exited with code {r.exit_code}: {r.stderr}"

        # The directory with content should still exist
        assert os.path.isfile(test_file), \
            "htcacheclean -t removed a non-empty directory"

        # Clean up
        if os.path.isdir(cache_root):
            shutil.rmtree(cache_root)
