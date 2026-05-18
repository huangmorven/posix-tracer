import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.tracer_module import tracer


class FakeWriter:
    def __init__(self):
        self.lines = []

    def write_line(self, line):
        self.lines.append(line)


class FormatterTest(unittest.TestCase):
    def make_event(self, **overrides):
        values = {
            "timestamp_ns": 1_710_000_000_123_456_000,
            "pid": 1234,
            "tid": 1234,
            "comm": "python3",
            "syscall": "getxattr",
            "matched": "path",
            "latency_ns": 34_000,
            "ret": 0,
            "errno": None,
            "args_text": '"/mnt/objstore/a", name="security.selinux", size=255',
        }
        values.update(overrides)
        return tracer.TraceEvent(**values)

    def test_success_event_contains_return_value(self):
        line = tracer.format_event_line(self.make_event(ret=5), compact=True)
        self.assertEqual(line, 'getxattr("/mnt/objstore/a", name="security.selinux", size=255) = 5')

    def test_failed_event_contains_errno(self):
        line = tracer.format_event_line(self.make_event(ret=-1, errno=95), compact=True)
        self.assertTrue(line.endswith("= -1 (errno=95)"))

    def test_default_event_contains_prefix(self):
        line = tracer.format_event_line(self.make_event(), compact=False)
        self.assertIn("pid=1234", line)
        self.assertIn("comm=python3", line)
        self.assertIn("latency=34us", line)
        self.assertIn("matched=path", line)
        self.assertTrue(line.startswith("["))

    def test_compact_event_omits_prefix(self):
        line = tracer.format_event_line(self.make_event(), compact=True)
        self.assertFalse(line.startswith("["))

    def test_latency_format_rounds_to_microseconds(self):
        self.assertEqual(tracer.format_latency(34_000), "34us")

    def test_event_time_converts_monotonic_timestamp_to_wall_clock(self):
        with patch.object(tracer.time, "time_ns", return_value=100_000_000_000), patch.object(
            tracer.time, "monotonic_ns", return_value=10_000_000_000
        ):
            self.assertEqual(tracer._monotonic_to_epoch_ns(5_000_000_000), 95_000_000_000)
            self.assertEqual(tracer._format_time(5_000_000_000), "00:01:35.000000")

    def test_runtime_closes_open_perf_event_tables(self):
        class FakeEventsTable:
            def __init__(self):
                self._open_key_fds = {0: -1, 1: -1}
                self.closed = []

            def __delitem__(self, key):
                self.closed.append(key)
                del self._open_key_fds[key]

        runtime = tracer.TracerRuntime(self.make_config())
        events_table = FakeEventsTable()
        runtime._events_tables.append(events_table)

        runtime._close_events_tables()

        self.assertEqual(events_table.closed, [0, 1])
        self.assertEqual(events_table._open_key_fds, {})

    def test_fd_args_are_preserved(self):
        line = tracer.format_event_line(
            self.make_event(syscall="fstat", args_text="fd=5</mnt/objstore/a>"),
            compact=True,
        )
        self.assertIn("fd=5</mnt/objstore/a>", line)

    def test_zero_valued_syscall_args_are_preserved(self):
        runtime = tracer.TracerRuntime(self.make_config())
        base_record = {
            "matched_mask": 1,
            "fd": 5,
            "dirfd": -100,
            "flags": 0,
            "mode": 0,
            "size": 0,
            "offset": 0,
            "request": 0,
            "path1": b"/mnt/objstore/a\0",
            "path2": b"\0",
        }

        cases = [
            ("openat", "flags=0", "mode=0"),
            ("truncate", "size=0", None),
            ("lseek", "offset=0", None),
            ("fcntl", "cmd=0", None),
            ("flock", "op=0", None),
            ("fchmod", "mode=0", None),
        ]
        for syscall, expected_arg, extra_expected_arg in cases:
            with self.subTest(syscall=syscall):
                record = SimpleNamespace(**base_record)
                text = runtime._format_args_text(syscall, record)

                self.assertIn(expected_arg, text)
                if extra_expected_arg is not None:
                    self.assertIn(extra_expected_arg, text)

    def test_fchmod_formats_second_arg_as_octal_mode(self):
        runtime = tracer.TracerRuntime(self.make_config())
        record = SimpleNamespace(
            matched_mask=4,
            fd=5,
            dirfd=-1,
            flags=0,
            mode=0o600,
            size=0,
            offset=0,
            request=0,
            path1=b"/mnt/objstore/a\0",
            path2=b"\0",
        )

        text = runtime._format_args_text("fchmod", record)

        self.assertIn("fd=5</mnt/objstore/a>", text)
        self.assertIn("mode=600", text)
        self.assertNotIn("flags=", text)

    def test_flock_formats_second_arg_as_operation(self):
        runtime = tracer.TracerRuntime(self.make_config())
        record = SimpleNamespace(
            matched_mask=4,
            fd=5,
            dirfd=-1,
            flags=2,
            mode=0,
            size=0,
            offset=0,
            request=0,
            path1=b"/mnt/objstore/a\0",
            path2=b"\0",
        )

        text = runtime._format_args_text("flock", record)

        self.assertIn("fd=5</mnt/objstore/a>", text)
        self.assertIn("op=2", text)
        self.assertNotIn("flags=", text)

    def test_xattr_name_is_rendered_when_capture_is_enabled(self):
        config = self.make_config(capture_xattr_name=True)
        runtime = tracer.TracerRuntime(config)
        record = SimpleNamespace(
            matched_mask=1,
            fd=-1,
            dirfd=-1,
            flags=0,
            mode=0,
            size=255,
            offset=0,
            request=0,
            path1=b"/mnt/objstore/a\0",
            path2=b"\0",
            xattr_name=b"security.selinux\0",
        )

        text = runtime._format_args_text("getxattr", record)

        self.assertIn("name='security.selinux'", text)
        self.assertIn("size=255", text)

    def test_xattr_name_is_not_rendered_by_default(self):
        runtime = tracer.TracerRuntime(self.make_config())
        record = SimpleNamespace(
            matched_mask=1,
            fd=-1,
            dirfd=-1,
            flags=0,
            mode=0,
            size=255,
            offset=0,
            request=0,
            path1=b"/mnt/objstore/a\0",
            path2=b"\0",
            xattr_name=b"security.selinux\0",
        )

        text = runtime._format_args_text("getxattr", record)

        self.assertNotIn("name=", text)
        self.assertIn("size=255", text)

    def test_runtime_decodes_bpf_record_into_trace_event(self):
        runtime = tracer.TracerRuntime(self.make_config())
        runtime._syscall_names_by_id = {1: "openat"}
        record = SimpleNamespace(
            timestamp_ns=1000,
            pid=10,
            tid=11,
            comm=b"touch\0",
            syscall_id=1,
            matched_mask=1,
            latency_ns=2500,
            ret=3,
            errno_value=0,
            fd=-1,
            dirfd=-100,
            flags=0,
            mode=0,
            size=0,
            offset=0,
            request=0,
            path1=b"/mnt/objstore/a\0",
            path2=b"\0",
        )

        event = runtime._trace_event_from_record(record)

        self.assertEqual(event.syscall, "openat")
        self.assertEqual(event.comm, "touch")
        self.assertEqual(event.matched, "path")
        self.assertEqual(event.ret, 3)
        self.assertIn("/mnt/objstore/a", event.args_text)
        self.assertIn("flags=0", event.args_text)
        self.assertIn("mode=0", event.args_text)

    def test_handle_event_decodes_default_ctypes_record_without_xattr_name(self):
        runtime = tracer.TracerRuntime(self.make_config())
        runtime._syscall_names_by_id = {1: "getxattr"}
        runtime._writer = FakeWriter()
        record = self.make_ctypes_record(
            tracer.PerfEventRecord,
            syscall_id=1,
            size=255,
            path1=b"/mnt/objstore/a\0",
        )

        runtime._handle_event(0, tracer.ctypes.pointer(record), tracer.ctypes.sizeof(record))

        self.assertEqual(len(runtime._writer.lines), 1)
        self.assertIn("getxattr('/mnt/objstore/a', size=255)", runtime._writer.lines[0])
        self.assertNotIn("name=", runtime._writer.lines[0])

    def test_handle_event_decodes_xattr_ctypes_record_when_capture_is_enabled(self):
        runtime = tracer.TracerRuntime(self.make_config(capture_xattr_name=True))
        runtime._syscall_names_by_id = {1: "getxattr"}
        runtime._writer = FakeWriter()
        record = self.make_ctypes_record(
            tracer.PerfEventRecordWithXattrName,
            syscall_id=1,
            size=255,
            path1=b"/mnt/objstore/a\0",
            xattr_name=b"security.selinux\0",
        )

        runtime._handle_event(0, tracer.ctypes.pointer(record), tracer.ctypes.sizeof(record))

        self.assertEqual(len(runtime._writer.lines), 1)
        self.assertIn("name='security.selinux'", runtime._writer.lines[0])
        self.assertIn("size=255", runtime._writer.lines[0])

    def test_handle_event_formats_time_with_cached_clock_offset(self):
        runtime = tracer.TracerRuntime(self.make_config())
        runtime._clock_offset_ns = 90_000_000_000
        runtime._syscall_names_by_id = {1: "getxattr"}
        runtime._writer = FakeWriter()
        record = self.make_ctypes_record(
            tracer.PerfEventRecord,
            timestamp_ns=5_000_000_000,
            syscall_id=1,
            size=255,
            path1=b"/mnt/objstore/a\0",
        )

        with patch.object(tracer.time, "time_ns", side_effect=AssertionError("clock offset was not cached")):
            runtime._handle_event(0, tracer.ctypes.pointer(record), tracer.ctypes.sizeof(record))

        self.assertEqual(len(runtime._writer.lines), 1)
        self.assertTrue(runtime._writer.lines[0].startswith("[00:01:35.000000 "), msg=runtime._writer.lines[0])

    def make_ctypes_record(self, record_type, **overrides):
        record = record_type()
        values = {
            "timestamp_ns": 1000,
            "pid": 10,
            "tid": 11,
            "comm": b"touch\0",
            "syscall_id": 1,
            "matched_mask": 1,
            "latency_ns": 2500,
            "ret": 0,
            "errno_value": 0,
            "fd": -1,
            "dirfd": -1,
            "flags": 0,
            "mode": 0,
            "size": 0,
            "offset": 0,
            "request": 0,
            "path1": b"\0",
            "path2": b"\0",
        }
        values.update(overrides)
        for key, value in values.items():
            setattr(record, key, value)
        return record

    def make_config(self, capture_xattr_name=False):
        return tracer.TracerConfig(
            target_dir="/mnt/objstore",
            target_dir_realpath="/mnt/objstore",
            output_path=None,
            duration_sec=None,
            follow=False,
            compact=False,
            capture_xattr_name=capture_xattr_name,
        )


if __name__ == "__main__":
    unittest.main()
