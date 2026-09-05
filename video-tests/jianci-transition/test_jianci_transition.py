import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("transition_runner", ROOT / "run_test.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = runner.read_config()

    def test_each_model_has_native_correct_payload(self):
        refs = ["https://example.com/modern.png", "https://example.com/ancient.png"]
        payloads = [runner.build_payload(m, self.cfg, refs) for m in self.cfg["models"]]
        self.assertTrue(payloads[0]["generate_audio"])
        self.assertTrue(payloads[1]["audio"])
        self.assertEqual(payloads[2]["resolution"], "768P")
        self.assertEqual(payloads[2]["ratio"], "16:9")
        self.assertNotIn("aspect_ratio", payloads[2])
        self.assertTrue(all(p["reference_images"] == refs and p["duration"] == 10 for p in payloads))

    def test_expensive_settings_rejected(self):
        for field, value in [("duration", 15), ("resolution", "720p")]:
            cfg = copy.deepcopy(self.cfg)
            cfg["models"][0]["settings"][field] = value
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.json"
                path.write_text(json.dumps(cfg), encoding="utf-8")
                with self.assertRaises(ValueError):
                    runner.read_config(path)

    def test_missing_audio_setting_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["models"][0]["settings"]["generate_audio"] = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.read_config(path)

    def test_output_extraction_ignores_reference_and_status_urls(self):
        data = {
            "status_url": "https://example.com/status",
            "reference_images": ["https://example.com/private.png"],
            "output": {"video": {"url": "https://example.com/result.mp4"}},
        }
        self.assertEqual(runner.output_urls(data), ["https://example.com/result.mp4"])

    def test_missing_key_stops_before_request(self):
        with self.assertRaises(RuntimeError):
            runner.Gateway("")

    def test_api_credentials_cannot_follow_redirect(self):
        with self.assertRaises(RuntimeError):
            runner.NoAuthRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_existing_report_prevents_duplicate_charges(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "report.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(RuntimeError), patch.object(runner.Gateway, "request") as request:
                runner.execute(self.cfg, [], {}, out)
            request.assert_not_called()

    def test_dry_run_never_contacts_provider(self):
        with patch.dict(os.environ, {"SEGMIND_TEST_EXECUTE": "0"}):
            with patch.object(runner.Gateway, "request") as request:
                self.assertEqual(runner.main(), 0)
            request.assert_not_called()

    def test_latest_scene_references_are_valid(self):
        self.assertEqual(len(runner.check_images(self.cfg)), 2)


if __name__ == "__main__":
    unittest.main()
