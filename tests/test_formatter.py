import unittest
from types import SimpleNamespace

import fuse_posix_tracer as tracer


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

    def test_fd_args_are_preserved(self):
        line = tracer.format_event_line(
            self.make_event(syscall="fstat", args_text="fd=5</mnt/objstore/a>"),
            compact=True,
        )
        self.assertIn("fd=5</mnt/objstore/a>", line)

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

    def make_config(self):
        return tracer.TracerConfig(
            target_dir="/mnt/objstore",
            target_dir_realpath="/mnt/objstore",
            output_path=None,
            duration_sec=None,
            follow=False,
            compact=False,
        )


if __name__ == "__main__":
    unittest.main()
