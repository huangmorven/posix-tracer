import io
import tempfile
import unittest
from pathlib import Path

import fuse_posix_tracer as tracer


class OutputWriterTest(unittest.TestCase):
    def test_writes_to_stdout_when_output_path_is_missing(self):
        stdout = io.StringIO()
        writer = tracer.OutputWriter(output_path=None, follow=False, stdout=stdout)
        writer.write_line("line1")
        writer.close()
        self.assertEqual(stdout.getvalue(), "line1\n")

    def test_writes_to_file_when_output_path_is_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir, "trace.log")
            stdout = io.StringIO()
            writer = tracer.OutputWriter(output_path=str(output_path), follow=False, stdout=stdout)
            writer.write_line("line1")
            writer.close()
            self.assertEqual(output_path.read_text(), "line1\n")
            self.assertEqual(stdout.getvalue(), "")

    def test_follow_writes_to_file_and_stdout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir, "trace.log")
            stdout = io.StringIO()
            writer = tracer.OutputWriter(output_path=str(output_path), follow=True, stdout=stdout)
            writer.write_line("line1")
            writer.close()
            self.assertEqual(output_path.read_text(), "line1\n")
            self.assertEqual(stdout.getvalue(), "line1\n")

    def test_invalid_output_path_raises_user_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(tracer.UserError):
                tracer.OutputWriter(output_path=tmpdir, follow=False, stdout=io.StringIO())

    def test_close_is_idempotent_and_flushes(self):
        stdout = io.StringIO()
        writer = tracer.OutputWriter(output_path=None, follow=False, stdout=stdout)
        writer.write_line("line1")
        writer.flush()
        writer.close()
        writer.close()
        self.assertEqual(stdout.getvalue(), "line1\n")


if __name__ == "__main__":
    unittest.main()
