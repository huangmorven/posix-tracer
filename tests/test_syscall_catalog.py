import unittest

from tests.tracer_module import tracer


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

    def test_fd_map_dependent_syscalls_share_one_bpf_group(self):
        enabled = sorted(tracer.BUSINESS_SYSCALLS | tracer.FD_MAINTENANCE_SYSCALLS)

        groups = tracer.group_syscalls_for_bpf(enabled, path_chunk_size=3)
        fd_groups = [
            set(group)
            for group in groups
            if any(tracer._uses_fd_map(syscall) for syscall in group)
        ]
        fd_group = fd_groups[0]

        self.assertEqual(len(fd_groups), 1)
        for syscall in enabled:
            with self.subTest(syscall=syscall):
                if tracer._uses_fd_map(syscall):
                    self.assertIn(syscall, fd_group)
                else:
                    self.assertNotIn(syscall, fd_group)

    def test_filtered_event_syscalls_include_fd_helpers_without_emitting_them(self):
        trace_syscalls = tracer.syscalls_to_trace_for_events({"fstat"})

        self.assertIn("fstat", trace_syscalls)
        self.assertTrue(tracer.FD_PRODUCER_SYSCALLS.issubset(trace_syscalls))
        self.assertTrue(tracer.FD_MAINTENANCE_SYSCALLS.issubset(trace_syscalls))

        source = tracer.build_bpf_source(
            "/mnt/objstore",
            ["openat", "fstat", "close"],
            event_syscalls={"fstat"},
        )

        self.assertIn("trace_exit_openat", source)
        self.assertIn("handle_exit(ctx, 1, 0, 1, 0)", source)
        self.assertIn("handle_exit(ctx, 2, 1, 0, 0)", source)
        self.assertIn("handle_exit(ctx, 3, 0, 0, 1)", source)

    def test_path_only_filtered_syscalls_do_not_add_fd_helpers(self):
        self.assertEqual(tracer.syscalls_to_trace_for_events({"statx"}), {"statx"})

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
            "MAX_CLOSE_RANGE_FDS 64",
        ]
        for part in expected_parts:
            with self.subTest(part=part):
                self.assertIn(part, source)
        self.assertNotIn("MAX_XATTR_NAME_LEN", source)
        self.assertNotIn("char xattr_name", source)
        self.assertNotIn("bpf_probe_read_str(&entry->xattr_name", source)
        self.assertNotIn("event->xattr_name", source)

    def test_xattr_name_capture_is_opt_in(self):
        source = tracer.build_bpf_source(
            "/mnt/objstore",
            ["getxattr", "setxattr", "listxattr"],
            capture_xattr_name=True,
        )

        self.assertIn("#define MAX_XATTR_NAME_LEN 256", source)
        self.assertIn("char xattr_name[MAX_XATTR_NAME_LEN]", source)
        self.assertIn("bpf_probe_read_str(&entry->xattr_name", source)
        self.assertIn("sizeof(event->xattr_name)", source)
        self.assertIn("handle_enter(ctx, 1, 0, -1, -1, -1, -1, 3, -1, -1, -1, 1)", source)
        self.assertIn("handle_enter(ctx, 2, 0, -1, -1, 4, -1, 3, -1, -1, -1, 1)", source)
        self.assertIn("handle_enter(ctx, 3, 0, -1, -1, -1, -1, 2, -1, -1, -1, -1)", source)

    def test_ctypes_perf_event_layout_keeps_xattr_name_opt_in(self):
        default_fields = [name for name, _type in tracer.PerfEventRecord._fields_]
        xattr_fields = [name for name, _type in tracer.PerfEventRecordWithXattrName._fields_]

        self.assertEqual(default_fields, [name for name, _type in tracer.PERF_EVENT_RECORD_FIELDS])
        self.assertNotIn("xattr_name", default_fields)
        self.assertEqual(xattr_fields, default_fields + ["xattr_name"])
        self.assertEqual(
            tracer.ctypes.sizeof(tracer.PerfEventRecordWithXattrName),
            tracer.ctypes.sizeof(tracer.PerfEventRecord) + tracer.MAX_XATTR_NAME_LEN,
        )
        for field_name in default_fields:
            with self.subTest(field_name=field_name):
                self.assertEqual(
                    getattr(tracer.PerfEventRecord, field_name).offset,
                    getattr(tracer.PerfEventRecordWithXattrName, field_name).offset,
                )

    def test_close_range_cleanup_uses_bounded_unroll(self):
        source = tracer.build_bpf_source("/mnt/objstore", ["close_range"])

        self.assertIn("#define MAX_CLOSE_RANGE_FDS 64", source)
        self.assertIn("i < MAX_CLOSE_RANGE_FDS", source)
        self.assertNotIn("i < 256", source)

    def test_each_business_syscall_has_path_or_fd_match_input(self):
        for syscall in sorted(tracer.BUSINESS_SYSCALLS):
            with self.subTest(syscall=syscall):
                path1_idx, path2_idx, fd_idx = tracer._syscall_profile(syscall)[:3]
                self.assertTrue(
                    path1_idx >= 0 or path2_idx >= 0 or fd_idx >= 0,
                    msg=f"{syscall} cannot match target path or tracked fd",
                )

    def test_profiles_cover_path_syscalls_that_are_easy_to_miss(self):
        expected = {
            "lchown": (0, -1, -1),
            "utime": (0, -1, -1),
            "utimes": (0, -1, -1),
            "symlinkat": (0, 2, -1),
        }
        for syscall, expected_prefix in expected.items():
            with self.subTest(syscall=syscall):
                self.assertEqual(tracer._syscall_profile(syscall)[:3], expected_prefix)


if __name__ == "__main__":
    unittest.main()
