import unittest

from tests.tracer_module import tracer


class SummaryTest(unittest.TestCase):
    def make_config(self, compact=False):
        return tracer.TracerConfig(
            target_dir="/mnt/objstore",
            target_dir_realpath="/mnt/objstore",
            output_path=None,
            duration_sec=None,
            follow=False,
            compact=compact,
        )

    def make_event(self, syscall="openat", ret=0, errno_value=None):
        return tracer.TraceEvent(
            timestamp_ns=1,
            pid=1,
            tid=1,
            comm="cmd",
            syscall=syscall,
            matched="path",
            latency_ns=1000,
            ret=ret,
            errno=errno_value,
            args_text='"/mnt/objstore/a"',
        )

    def test_header_contains_capture_context(self):
        header = tracer.format_header(
            self.make_config(compact=True),
            kernel="5.15.0-test",
            bcc_version="0.30.0",
            skipped_syscalls=["openat2", "faccessat2"],
        )
        expected_parts = [
            "# target_dir=/mnt/objstore",
            "# target_dir_realpath=/mnt/objstore",
            "# kernel=5.15.0-test",
            "# bcc_version=0.30.0",
            "# mode=exit-only",
            "# output_format=strace-like",
            "# compact=true",
            "# skipped_syscalls=openat2,faccessat2",
        ]
        for part in expected_parts:
            with self.subTest(part=part):
                self.assertIn(part, header)

    def test_summary_counts_events_failures_lost_syscalls_and_errno(self):
        summary = tracer.Summary()
        summary.record_event(self.make_event(syscall="openat", ret=5))
        summary.record_event(self.make_event(syscall="setxattr", ret=-1, errno_value=95))
        summary.record_lost(3)

        self.assertEqual(summary.total_events, 2)
        self.assertEqual(summary.failed_events, 1)
        self.assertEqual(summary.lost_events, 3)
        self.assertEqual(summary.syscall_counts["openat"], 1)
        self.assertEqual(summary.syscall_counts["setxattr"], 1)
        self.assertEqual(summary.errno_counts[95], 1)

        text = tracer.format_summary(summary)
        self.assertIn("# total_events=2", text)
        self.assertIn("# failed_events=1", text)
        self.assertIn("# lost_events=3", text)
        self.assertIn("trace may be incomplete", text)
        self.assertIn("#   openat=1", text)
        self.assertIn("#   errno=95 count=1", text)


if __name__ == "__main__":
    unittest.main()
