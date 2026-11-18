import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_app(self, *arguments, input_text=""):
        return subprocess.run([sys.executable, "-m", "storepilot", *arguments],
                              input=input_text, capture_output=True, text=True,
                              cwd=PROJECT_ROOT, timeout=10)

    def test_demo_displays_the_expected_draft_bill(self):
        result = self.run_app("--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TOTAL: INR 422.00", result.stdout)
        self.assertIn("DRAFT BILL", result.stdout)
        self.assertIn("No sale, stock, or payment has been saved", result.stdout)

    def test_recovers_from_bad_input_without_adding_it_to_the_bill(self):
        result = self.run_app(input_text="search sugar\nSUGAR-LOOSE 250 g\nSUGAR-PACK-1KG 0.5\nSUGAR-PACK-1KG 2\ndone\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("whole numbers", result.stdout)
        self.assertIn("TOTAL: INR 122.00", result.stdout)

    def test_loads_an_alternate_catalogue(self):
        rows = [{"code": "SOAP", "name": "Soap", "unit": "piece", "price": "4.25"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            result = self.run_app("--catalogue", str(path), input_text="SOAP 2\ndone\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TOTAL: INR 8.50", result.stdout)

    def test_missing_catalogue_has_a_readable_error_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_app("--catalogue", str(Path(directory) / "missing.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Cannot load catalogue", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_quit_and_end_of_input_cancel_the_draft(self):
        for input_text in ["SUGAR-LOOSE 250 g\nquit\n", ""]:
            with self.subTest(input_text=input_text):
                result = self.run_app(input_text=input_text)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Draft cancelled", result.stdout)
                self.assertNotIn("TOTAL:", result.stdout)

    def test_empty_bill_and_unknown_product_are_rejected(self):
        result = self.run_app(input_text="done\nMISSING 1\nquit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("at least one", result.stdout)
        self.assertIn("Unknown product", result.stdout)

    def test_malformed_item_recovers_and_allows_a_valid_bill(self):
        result = self.run_app(input_text="SOAP\nSUGAR-LOOSE 1 kg extra\nSUGAR-LOOSE 0.5 kg\ndone\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Use PRODUCT_CODE QUANTITY [UNIT]", result.stdout)
        self.assertIn("TOTAL: INR 24.00", result.stdout)


if __name__ == "__main__":
    unittest.main()
