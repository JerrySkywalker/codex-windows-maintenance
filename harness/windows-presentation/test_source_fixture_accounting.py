"""Focused accounting cannot be omitted, narrowed or silently converted to full."""
import unittest

from source_fixture_contract import TEST_NAME
from source_validation import FOCUSED_SELECTION, validate_accounting, validate_selection


class SourceFixtureAccountingTests(unittest.TestCase):
    def log(self, total, passed, skipped):
        return f"PASS [1s] {TEST_NAME}\nSummary [2s] {total} tests run: {passed} passed, {skipped} skipped"

    def test_omitted_mode_requires_all_68_and_zero_skips(self):
        self.assertEqual(validate_accounting(self.log(68, 68, 0)),
                         {"testsRun": 68, "passed": 68, "skipped": 0})
        for log in (self.log(1, 1, 0), self.log(67, 67, 1), f"PASS {TEST_NAME}"):
            with self.subTest(log=log), self.assertRaises(ValueError):
                validate_accounting(log)

    def test_narrowed_selection_cannot_claim_focused_pass(self):
        validate_selection(FOCUSED_SELECTION)
        for selection in ([], ["-p", "codex-app-server-daemon", "--lib"],
                          FOCUSED_SELECTION + ["-E", f"test({TEST_NAME})"]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                validate_selection(selection)

    def test_full_suite_is_explicit_and_requires_default_selection(self):
        validate_selection([], full_suite=True)
        with self.assertRaises(ValueError):
            validate_selection(FOCUSED_SELECTION, full_suite=True)
        with self.assertRaises(ValueError):
            validate_accounting(self.log(68, 68, 0), full_suite=True)
        with self.assertRaises(ValueError):
            validate_accounting(self.log(1000, 1000, 2), full_suite=True)
        with self.assertRaises(ValueError):
            validate_accounting(self.log(1000, 1000, 2), full_suite=True, expected_skips=1)
        self.assertEqual(validate_accounting(self.log(1000, 1000, 2), full_suite=True, expected_skips=2),
                         {"testsRun": 1000, "passed": 1000, "skipped": 2})


if __name__ == "__main__":
    unittest.main()
