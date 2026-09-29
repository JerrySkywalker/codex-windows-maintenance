"""Grouped nextest runs must cover every discovered source test exactly once."""
import unittest

from source_fixture_contract import TEST_NAME
from source_validation import FOCUSED_SELECTION, validate_accounting, validate_selection


class SourceFixtureAccountingTests(unittest.TestCase):
    def suites(self, pty=26, rest=42, ignored_pty=0, ignored_rest=0):
        return {
            "pty": {"package-name": "codex-utils-pty", "testcases": {
                f"pty_{i}": {"ignored": i < ignored_pty} for i in range(pty)}},
            "daemon": {"package-name": "codex-app-server-daemon", "testcases": {
                f"rest_{i}": {"ignored": i < ignored_rest} for i in range(rest)}},
        }

    def log(self, total, passed, skipped, positive=False):
        prefix = f"PASS [1s] {TEST_NAME}\n" if positive else ""
        return f"{prefix}Summary [2s] {total} tests run: {passed} passed, {skipped} skipped"

    def test_focused_groups_cover_68_with_no_skips(self):
        logs = {"pty": self.log(26, 26, 0), "daemon": self.log(42, 42, 0, True)}
        self.assertEqual(validate_accounting(logs, self.suites()), {
            "testsRun": 68, "passed": 68, "skipped": 0,
            "groups": {"pty": {"testsRun": 26, "passed": 26, "skipped": 0},
                       "daemon": {"testsRun": 42, "passed": 42, "skipped": 0}}})
        for bad in (
            {**logs, "pty": self.log(25, 25, 1)},
            {**logs, "daemon": self.log(41, 41, 1, True)},
            {**logs, "daemon": self.log(42, 42, 0)},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_accounting(bad, self.suites())
        with self.assertRaises(ValueError):
            validate_accounting(logs, self.suites(pty=25, rest=43))

    def test_selection_cannot_be_narrowed_by_caller(self):
        validate_selection(FOCUSED_SELECTION)
        for selection in ([], ["-p", "codex-app-server-daemon", "--lib"],
                          FOCUSED_SELECTION + ["-E", f"test({TEST_NAME})"]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                validate_selection(selection)

    def test_full_suite_accounts_for_ignored_and_filtered_pty(self):
        validate_selection([], full_suite=True)
        with self.assertRaises(ValueError):
            validate_selection(FOCUSED_SELECTION, full_suite=True)
        suites = self.suites(pty=26, rest=100, ignored_pty=1, ignored_rest=2)
        logs = {"pty": self.log(25, 25, 1),
                "workspace-rest": self.log(98, 98, 28, True)}
        self.assertEqual(validate_accounting(logs, suites, full_suite=True)["skipped"], 3)
        for bad in (
            {**logs, "pty": self.log(25, 25, 0)},
            {**logs, "workspace-rest": self.log(98, 98, 27, True)},
            {**logs, "workspace-rest": self.log(98, 97, 28, True)},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_accounting(bad, suites, full_suite=True)


if __name__ == "__main__":
    unittest.main()
