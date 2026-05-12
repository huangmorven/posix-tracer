import tempfile
import unittest
from pathlib import Path

from tests.tracer_module import tracer


class CliTest(unittest.TestCase):
    def test_dir_is_required(self):
        with self.assertRaises(SystemExit):
            tracer.parse_args([])

    def test_parse_supported_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = tracer.parse_args([
                "--dir",
                tmpdir,
                "--output",
                "trace.log",
                "--duration",
                "1.5",
                "--follow",
                "--compact",
            ])
            config = tracer.build_config(args)

        self.assertEqual(config.target_dir, tracer.normalize_target_dir(str(Path(tmpdir).absolute())))
        self.assertEqual(config.target_dir_realpath, str(Path(tmpdir).resolve()))
        self.assertEqual(config.output_path, "trace.log")
        self.assertEqual(config.duration_sec, 1.5)
        self.assertTrue(config.follow)
        self.assertTrue(config.compact)

    def test_short_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = tracer.parse_args(["-d", tmpdir, "-o", "out.log", "-t", "2"])
            config = tracer.build_config(args)

        self.assertEqual(config.output_path, "out.log")
        self.assertEqual(config.duration_sec, 2.0)
        self.assertFalse(config.follow)
        self.assertFalse(config.compact)

    def test_missing_target_directory_raises_user_error(self):
        args = tracer.parse_args(["--dir", "/path/that/does/not/exist"])
        with self.assertRaises(tracer.UserError):
            tracer.build_config(args)

    def test_target_must_be_directory(self):
        with tempfile.NamedTemporaryFile() as tmpfile:
            args = tracer.parse_args(["--dir", tmpfile.name])
            with self.assertRaises(tracer.UserError):
                tracer.build_config(args)

    def test_target_dir_preserves_user_path_for_prefix_matching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = Path(tmpdir, "real")
            real_dir.mkdir()
            link_dir = Path(tmpdir, "link")
            link_dir.symlink_to(real_dir, target_is_directory=True)
            args = tracer.parse_args(["--dir", str(link_dir)])
            config = tracer.build_config(args)

        self.assertEqual(config.target_dir, tracer.normalize_target_dir(str(link_dir.absolute())))
        self.assertEqual(config.target_dir_realpath, str(real_dir.resolve()))


if __name__ == "__main__":
    unittest.main()
