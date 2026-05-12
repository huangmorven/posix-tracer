import tempfile
import unittest
from pathlib import Path

import fuse_posix_tracer as tracer


class TracepointDiscoveryTest(unittest.TestCase):
    def create_tracepoint(self, root, name, enter=True, exit=True):
        if enter:
            Path(root, f"sys_enter_{name}").mkdir(parents=True)
        if exit:
            Path(root, f"sys_exit_{name}").mkdir(parents=True)

    def test_discovers_enabled_and_skipped_syscalls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.create_tracepoint(tmpdir, "openat", enter=True, exit=True)
            self.create_tracepoint(tmpdir, "statx", enter=True, exit=False)
            self.create_tracepoint(tmpdir, "renameat2", enter=False, exit=True)

            enabled, skipped = tracer.discover_tracepoints(
                ["openat", "statx", "renameat2"], tracing_events_dir=tmpdir
            )

        self.assertEqual(enabled, ["openat"])
        self.assertEqual(skipped, ["statx", "renameat2"])

    def test_missing_tracing_directory_skips_all(self):
        enabled, skipped = tracer.discover_tracepoints(
            ["openat", "statx"], tracing_events_dir="/path/that/does/not/exist"
        )
        self.assertEqual(enabled, [])
        self.assertEqual(skipped, ["openat", "statx"])


if __name__ == "__main__":
    unittest.main()
