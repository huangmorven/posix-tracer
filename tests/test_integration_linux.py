from contextlib import contextmanager
import os
import platform
import signal
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
    XATTR_NAME = "user.posix_tracer_key"

    def run_tracer_with_workload(self, target_dir, output_path, workload, duration="2", extra_args=None):
        proc = self.start_tracer(target_dir, output_path, duration=duration, extra_args=extra_args)
        try:
            workload()
        except Exception:
            proc.terminate()
            proc.communicate(timeout=5)
            raise
        stdout, stderr = proc.communicate(timeout=8)
        self.assertEqual(proc.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
        return output_path.read_text()

    def start_tracer(self, target_dir, output_path, duration="2", extra_args=None):
        project_root = Path(__file__).resolve().parents[1]
        tracer_script = project_root / "posix-tracer"
        command = [
            sys.executable,
            str(tracer_script),
            "--dir",
            str(target_dir),
            "--output",
            str(output_path),
            "--duration",
            duration,
        ]
        if extra_args:
            command.extend(extra_args)
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if output_path.exists() and "# tracing_ready=true" in output_path.read_text():
                break
            time.sleep(0.1)
        else:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            self.fail(f"tracer did not become ready\nstdout={stdout}\nstderr={stderr}")
        return proc

    def event_lines(self, log_text):
        return [line for line in log_text.splitlines() if line and not line.startswith("#")]

    def run_xattr_workload(self, target_file):
        target_file.write_text("payload")
        os.setxattr(str(target_file), self.XATTR_NAME, b"value")
        self.assertEqual(os.getxattr(str(target_file), self.XATTR_NAME), b"value")
        self.assertIn(self.XATTR_NAME, os.listxattr(str(target_file)))
        os.removexattr(str(target_file), self.XATTR_NAME)

    def xattr_event_lines(self, log_text):
        return [line for line in self.event_lines(log_text) if "xattr(" in line]

    @contextmanager
    def bind_mounted_target(self, tmpdir):
        backing_dir = Path(tmpdir, "backing-target")
        mount_point = Path(tmpdir, "mounted-target")
        backing_dir.mkdir()
        mount_point.mkdir()
        result = subprocess.run(
            ["mount", "--bind", str(backing_dir), str(mount_point)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            self.skipTest(f"bind mount is not available: {result.stderr}")
        try:
            yield mount_point
        finally:
            subprocess.run(
                ["umount", str(mount_point)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

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

    def test_tracer_flushes_summary_after_sigterm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir, "target")
            target_dir.mkdir()
            output_path = Path(tmpdir, "trace.log")

            proc = self.start_tracer(target_dir, output_path, duration="30")
            proc.send_signal(signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=8)

            self.assertEqual(proc.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
            log_text = output_path.read_text()
            self.assertIn("# tracing_ready=true", log_text)
            self.assertIn("# summary:", log_text)
            self.assertIn("# total_events=", log_text)

    def test_tracer_captures_xattr_workload_without_name_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir, "trace.log")
            with self.bind_mounted_target(tmpdir) as target_dir:
                target_file = target_dir / "xattr-workload"
                log_text = self.run_tracer_with_workload(
                    target_dir,
                    output_path,
                    lambda: self.run_xattr_workload(target_file),
                )
            xattr_lines = self.xattr_event_lines(log_text)

            self.assertIn("# capture_xattr_name=false", log_text)
            self.assertIn("# xattr_name_buffer_bytes=0", log_text)
            self.assertTrue(any("setxattr(" in line and str(target_file) in line for line in xattr_lines), msg=log_text)
            self.assertTrue(any("getxattr(" in line and str(target_file) in line for line in xattr_lines), msg=log_text)
            self.assertTrue(any("removexattr(" in line and str(target_file) in line for line in xattr_lines), msg=log_text)
            self.assertFalse(any("name=" in line for line in xattr_lines), msg=log_text)
            self.assertFalse(any(self.XATTR_NAME in line for line in xattr_lines), msg=log_text)

    def test_tracer_captures_xattr_workload_with_name_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir, "trace.log")
            with self.bind_mounted_target(tmpdir) as target_dir:
                target_file = target_dir / "xattr-workload"
                log_text = self.run_tracer_with_workload(
                    target_dir,
                    output_path,
                    lambda: self.run_xattr_workload(target_file),
                    extra_args=["--capture-xattr-name"],
                )
            xattr_lines = self.xattr_event_lines(log_text)
            expected_name = f"name='{self.XATTR_NAME}'"

            self.assertIn("# capture_xattr_name=true", log_text)
            self.assertIn("# xattr_name_buffer_bytes=256", log_text)
            self.assertTrue(any("setxattr(" in line and expected_name in line for line in xattr_lines), msg=log_text)
            self.assertTrue(any("getxattr(" in line and expected_name in line for line in xattr_lines), msg=log_text)
            self.assertTrue(any("removexattr(" in line and expected_name in line for line in xattr_lines), msg=log_text)


if __name__ == "__main__":
    unittest.main()
