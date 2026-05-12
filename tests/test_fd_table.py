import unittest

import fuse_posix_tracer as tracer


class FdTableTest(unittest.TestCase):
    def test_open_and_resolve(self):
        table = tracer.FdTable()
        table.open(100, 5, "/mnt/objstore/a")
        self.assertEqual(table.resolve(100, 5), "/mnt/objstore/a")

    def test_close_removes_mapping(self):
        table = tracer.FdTable()
        table.open(100, 5, "/mnt/objstore/a")
        table.close(100, 5)
        self.assertIsNone(table.resolve(100, 5))

    def test_close_range_removes_only_range(self):
        table = tracer.FdTable()
        for fd in (3, 4, 5, 6):
            table.open(100, fd, f"/mnt/objstore/{fd}")
        table.close_range(100, 4, 5)
        self.assertEqual(table.resolve(100, 3), "/mnt/objstore/3")
        self.assertIsNone(table.resolve(100, 4))
        self.assertIsNone(table.resolve(100, 5))
        self.assertEqual(table.resolve(100, 6), "/mnt/objstore/6")

    def test_dup_copies_mapping(self):
        table = tracer.FdTable()
        table.open(100, 5, "/mnt/objstore/a")
        table.dup(100, 5, 8)
        self.assertEqual(table.resolve(100, 8), "/mnt/objstore/a")

    def test_dup_unknown_fd_does_not_create_mapping(self):
        table = tracer.FdTable()
        table.dup(100, 5, 8)
        self.assertIsNone(table.resolve(100, 8))

    def test_different_pids_do_not_share_fd_mapping(self):
        table = tracer.FdTable()
        table.open(100, 5, "/mnt/objstore/a")
        table.open(200, 5, "/mnt/objstore/b")
        self.assertEqual(table.resolve(100, 5), "/mnt/objstore/a")
        self.assertEqual(table.resolve(200, 5), "/mnt/objstore/b")


if __name__ == "__main__":
    unittest.main()
