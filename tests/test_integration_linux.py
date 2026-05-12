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
    def test_integration_environment_can_create_target_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(os.path.isdir(tmpdir))

    def test_tracer_captures_basic_metadata_workload(self):
        project_root = Path(__file__).resolve().parents[1]
        tracer_script = project_root / "fuse_posix_tracer.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir, "target")
            target_dir.mkdir()
            outside = Path(tmpdir, "outside")
            outside.write_text("data")
            output_path = Path(tmpdir, "trace.log")

            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(tracer_script),
                    "--dir",
                    str(target_dir),
                    "--output",
                    str(output_path),
                    "--duration",
                    "2",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.5)
            subprocess.run(["touch", str(target_dir / "a")], check=True)
            subprocess.run(["stat", str(target_dir / "a")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["mv", str(outside), str(target_dir / "b")], check=True)
            stdout, stderr = proc.communicate(timeout=5)

            self.assertEqual(proc.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
            log_text = output_path.read_text()
            self.assertIn("# fuse-posix-tracer started_at=", log_text)
            self.assertIn("# summary:", log_text)
            event_lines = [line for line in log_text.splitlines() if line and not line.startswith("#")]
            self.assertTrue(
                any(name in line for name in ("openat(", "statx(", "newfstatat(", "rename(", "renameat(", "renameat2(") for line in event_lines),
                msg=log_text,
            )
            self.assertFalse(any("read(" in line or "write(" in line or "close(" in line for line in event_lines))


if __name__ == "__main__":
    unittest.main()
