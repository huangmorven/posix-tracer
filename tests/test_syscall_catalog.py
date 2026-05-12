import unittest

import fuse_posix_tracer as tracer


class SyscallCatalogTest(unittest.TestCase):
    def test_groups_contain_specified_syscalls(self):
        expected = {
            "path_open": {"open", "openat", "openat2", "creat", "name_to_handle_at"},
            "metadata_read": {"stat", "lstat", "fstat", "newfstatat", "fstatat", "statx", "access", "faccessat", "faccessat2", "readlink", "readlinkat"},
            "metadata_write": {"chmod", "fchmod", "fchmodat", "chown", "fchown", "lchown", "fchownat", "utime", "utimes", "utimensat", "futimesat", "truncate", "ftruncate"},
            "directory": {"mkdir", "mkdirat", "rmdir", "getdents", "getdents64"},
            "link_rename_delete": {"link", "linkat", "symlink", "symlinkat", "unlink", "unlinkat", "rename", "renameat", "renameat2"},
            "fd_control": {"fcntl", "ioctl", "flock", "fsync", "fdatasync", "syncfs", "lseek"},
            "xattr": {"getxattr", "lgetxattr", "fgetxattr", "setxattr", "lsetxattr", "fsetxattr", "listxattr", "llistxattr", "flistxattr", "removexattr", "lremovexattr", "fremovexattr"},
            "space_control": {"fallocate"},
        }
        self.assertEqual(tracer.SYSCALL_GROUPS, expected)

    def test_business_syscalls_include_groups_but_not_excluded_io(self):
        grouped = set().union(*tracer.SYSCALL_GROUPS.values())
        self.assertTrue(grouped.issubset(tracer.BUSINESS_SYSCALLS))
        for syscall in ("read", "write", "close", "close_range"):
            with self.subTest(syscall=syscall):
                self.assertNotIn(syscall, tracer.BUSINESS_SYSCALLS)

    def test_fd_maintenance_and_producer_sets(self):
        for syscall in ("close", "close_range", "dup", "dup2", "dup3", "fcntl"):
            with self.subTest(syscall=syscall):
                self.assertIn(syscall, tracer.FD_MAINTENANCE_SYSCALLS)
        for syscall in ("open", "openat", "openat2", "creat"):
            with self.subTest(syscall=syscall):
                self.assertIn(syscall, tracer.FD_PRODUCER_SYSCALLS)

    def test_build_bpf_source_contains_required_sections(self):
        source = tracer.build_bpf_source("/mnt/objstore", ["openat", "statx"])
        self.assertIsInstance(source, str)
        expected_parts = [
            "BPF_HASH(entry_map",
            "BPF_HASH(fd_map",
            "BPF_PERF_OUTPUT(events)",
            "/mnt/objstore",
            "struct event_t",
            "handle_enter",
            "handle_exit",
            "events.perf_submit",
            "MAX_PATH_LEN 256",
            "MAX_XATTR_NAME_LEN 64",
        ]
        for part in expected_parts:
            with self.subTest(part=part):
                self.assertIn(part, source)


if __name__ == "__main__":
    unittest.main()
