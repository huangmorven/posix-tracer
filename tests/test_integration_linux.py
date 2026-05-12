import os
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


def bcc_available():
    try:
        import bcc  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(platform.system() == "Linux", "requires Linux")
@unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "requires root")
@unittest.skipUnless(bcc_available(), "requires BCC")
class LinuxIntegrationTest(unittest.TestCase):
    def run_tracer_with_workload(self, target_dir, output_path, workload, duration="2"):
        project_root = Path(__file__).resolve().parents[1]
        tracer_script = project_root / "posix-tracer"
        proc = subprocess.Popen(
            [
                sys.executable,
                str(tracer_script),
                "--dir",
                str(target_dir),
                "--output",
                str(output_path),
                "--duration",
                duration,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.5)
        workload()
        stdout, stderr = proc.communicate(timeout=8)
        self.assertEqual(proc.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
        return output_path.read_text()

    def event_lines(self, log_text):
        return [line for line in log_text.splitlines() if line and not line.startswith("#")]

    def test_integration_environment_can_create_target_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(os.path.isdir(tmpdir))

    def test_tracer_captures_basic_metadata_workload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir, "target")
            target_dir.mkdir()
            outside = Path(tmpdir, "outside")
            outside.write_text("data")
            output_path = Path(tmpdir, "trace.log")

            def workload():
                subprocess.run(["touch", str(target_dir / "a")], check=True)
                subprocess.run(["stat", str(target_dir / "a")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["mv", str(outside), str(target_dir / "b")], check=True)

            log_text = self.run_tracer_with_workload(target_dir, output_path, workload)
            self.assertIn("# posix-tracer started_at=", log_text)
            self.assertIn("# summary:", log_text)
            event_lines = self.event_lines(log_text)
            self.assertTrue(
                any(name in line for name in ("openat(", "statx(", "newfstatat(", "rename(", "renameat(", "renameat2(") for line in event_lines),
                msg=log_text,
            )
            self.assertFalse(any("read(" in line or "write(" in line or "close(" in line for line in event_lines))

    def test_tracer_captures_fd_based_operations_after_open(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir, "target")
            target_dir.mkdir()
            output_path = Path(tmpdir, "trace.log")
            target_file = target_dir / "fd-workload"

            def workload():
                script = (
                    "import os\n"
                    f"path = {str(target_file)!r}\n"
                    "fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)\n"
                    "try:\n"
                    "    os.fstat(fd)\n"
                    "    os.fchmod(fd, 0o600)\n"
                    "    os.ftruncate(fd, 16)\n"
                    "    os.lseek(fd, 0, os.SEEK_SET)\n"
                    "    os.fsync(fd)\n"
                    "finally:\n"
                    "    os.close(fd)\n"
                )
                subprocess.run([sys.executable, "-c", script], check=True)

            log_text = self.run_tracer_with_workload(target_dir, output_path, workload)
            event_lines = self.event_lines(log_text)
            self.assertTrue(any("openat(" in line and str(target_file) in line for line in event_lines), msg=log_text)
            self.assertTrue(
                any(
                    name in line and f"fd=" in line and str(target_file) in line
                    for name in ("fstat(", "fchmod(", "ftruncate(", "lseek(", "fsync(")
                    for line in event_lines
                ),
                msg=log_text,
            )

    def test_tracer_filters_out_paths_outside_target_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir, "target")
            target_dir.mkdir()
            sibling_dir = Path(tmpdir, "target-sibling")
            sibling_dir.mkdir()
            output_path = Path(tmpdir, "trace.log")

            def workload():
                subprocess.run(["touch", str(target_dir / "inside")], check=True)
                subprocess.run(["touch", str(sibling_dir / "outside")], check=True)
                subprocess.run(["stat", str(sibling_dir / "outside")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            log_text = self.run_tracer_with_workload(target_dir, output_path, workload)
            event_lines = self.event_lines(log_text)
            self.assertTrue(any(str(target_dir / "inside") in line for line in event_lines), msg=log_text)
            self.assertFalse(any(str(sibling_dir / "outside") in line for line in event_lines), msg=log_text)


if __name__ == "__main__":
    unittest.main()
