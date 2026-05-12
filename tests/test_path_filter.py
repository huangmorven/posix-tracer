import unittest

import fuse_posix_tracer as tracer


class PathFilterTest(unittest.TestCase):
    def test_normalize_target_dir_removes_trailing_slash(self):
        self.assertEqual(tracer.normalize_target_dir("/mnt/objstore/"), "/mnt/objstore")

    def test_path_under_target_table(self):
        target = tracer.normalize_target_dir("/mnt/objstore/")
        cases = [
            ("/mnt/objstore", True),
            ("/mnt/objstore/a.txt", True),
            ("/mnt/objstore/sub/a.txt", True),
            ("/mnt/objstore2/a.txt", False),
            ("/mnt/objstore-link/a.txt", False),
            ("/tmp/objstore/a.txt", False),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(tracer.is_path_under_target(path, target), expected)


if __name__ == "__main__":
    unittest.main()
