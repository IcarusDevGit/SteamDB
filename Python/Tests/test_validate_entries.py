"""Test chart parsing, CSV comparison, evidence, and artifact classification."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ValidateEntries
import workflow_paths
from validation_models import ChartIdentity, ValidationStatus


FIXTURES = Path(__file__).parent / "fixtures"


class ValidateEntriesTests(unittest.TestCase):
    """Verify validation status, evidence integrity, and command-line behavior."""
    def _csv(self, directory, identities, *, week="2026-08-04", name="input.csv"):
        """Create a minimal identity CSV whose enrichment values are irrelevant."""
        path = Path(directory) / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["week_date", "rank", "appid", "name", "rating"]
            )
            writer.writeheader()
            for rank, appid in identities:
                writer.writerow(
                    {"week_date": week, "rank": rank, "appid": appid, "name": "ignored", "rating": 0.5}
                )
        return path

    def test_models_digest_and_enrichment_independence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory, [(1, 10), (2, 20)])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(ValidateEntries.csv_sha256(path), digest)
            week, identities, duplicates, duplicate_apps = ValidateEntries.parse_csv_identities(path)
            self.assertEqual(week, "2026-08-04")
            self.assertEqual(identities, [ChartIdentity(1, 10), ChartIdentity(2, 20)])
            self.assertEqual((duplicates, duplicate_apps), ([], []))
            text = path.read_text(encoding="utf-8").replace("0.5", "0.9")
            path.write_text(text, encoding="utf-8")
            self.assertEqual(ValidateEntries.parse_csv_identities(path)[1], identities)

    def test_input_reports_duplicates_and_rejects_malformed_or_multiple_weeks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory, [(1, 10), (1, 10)])
            _, _, ranks, appids = ValidateEntries.parse_csv_identities(path)
            self.assertEqual(ranks, [1])
            self.assertEqual(appids, [10])
            with path.open("a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(["2026-08-11", 2, 20, "ignored", 0.5])
            with self.assertRaisesRegex(ValueError, "exactly one"):
                ValidateEntries.parse_csv_identities(path)
            malformed = self._csv(directory, [(0, -1)], name="malformed.csv")
            with self.assertRaisesRegex(ValueError, "out-of-range"):
                ValidateEntries.parse_csv_identities(malformed)

    def test_bootstrap_request_and_complete_chart_parsing(self):
        html = (FIXTURES / "steam_chart_bootstrap.html").read_text(encoding="utf-8")
        self.assertEqual(
            ValidateEntries.parse_chart_bootstrap(html),
            [ChartIdentity(1, 1001), ChartIdentity(2, 1002)],
        )
        request = ValidateEntries.complete_chart_request("2026-08-04")
        self.assertEqual(request["page_count"], 100)
        self.assertEqual(request["country_code"], "")
        self.assertEqual(request["start_date"], 1785801600)
        payload = json.loads((FIXTURES / "complete_chart.json").read_text(encoding="utf-8"))
        rows = payload["response"]["ranks"]
        self.assertEqual(len(ValidateEntries.parse_complete_chart(payload)), 100)
        with self.assertRaisesRegex(RuntimeError, "instead of 100"):
            ValidateEntries.parse_complete_chart({"response": {"ranks": rows[:99]}})

    def test_detailed_global_rows_normalize_chart_fields(self):
        rows = [{
            "rank": rank, "appid": 1000 + rank,
            "last_week_rank": rank + 1, "consecutive_weeks": rank,
            "item": {"name": f" Game {rank} "},
        } for rank in range(1, 101)]
        normalized = ValidateEntries.parse_complete_chart_rows({"response": {"ranks": rows}})
        self.assertEqual(normalized[0], {
            "rank": 1, "appid": 1001, "name": "Game 1",
            "last_week_rank": 2, "consecutive_weeks": 1,
        })
        duplicate = [dict(item) for item in rows]
        duplicate[-1]["appid"] = 1001
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            ValidateEntries.parse_complete_chart_rows({"response": {"ranks": duplicate}})

    def test_fetcher_anchors_page_and_requires_prefix(self):
        html = (FIXTURES / "steam_chart_bootstrap.html").read_text(encoding="utf-8")
        complete = [{"rank": rank, "appid": 1000 + rank} for rank in range(1, 101)]
        page_response = Mock(text=html)
        page_response.raise_for_status.return_value = None
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.json.return_value = {"response": {"ranks": complete}}
        session = Mock()
        session.get.side_effect = [page_response, api_response]
        url, rows = ValidateEntries.SteamChartFetcher(session)("2026-08-04")
        self.assertEqual(url, "https://store.steampowered.com/charts/topsellers/global/2026-08-04")
        self.assertEqual(len(rows), 100)
        self.assertEqual(session.get.call_args_list[0].args[0], url)

        bad_html = html.replace("1001", "9999")
        bad_page = Mock(text=bad_html)
        bad_page.raise_for_status.return_value = None
        session.get.side_effect = [bad_page, api_response]
        with self.assertRaisesRegex(RuntimeError, "prefix"):
            ValidateEntries.SteamChartFetcher(session)("2026-08-04")

    def test_detailed_fetcher_forces_global_request(self):
        html = (FIXTURES / "steam_chart_bootstrap.html").read_text(encoding="utf-8")
        complete = [{"rank": rank, "appid": 1000 + rank, "item": {"name": f"Game {rank}"}}
                    for rank in range(1, 101)]
        page = Mock(text=html)
        page.raise_for_status.return_value = None
        api = Mock()
        api.raise_for_status.return_value = None
        api.json.return_value = {"response": {"ranks": complete}}
        session = Mock()
        session.get.side_effect = [page, api]
        events = []
        _, rows = ValidateEntries.GlobalChartFetcher(session, reporter=events.append)("2026-08-04")
        request = json.loads(session.get.call_args_list[1].kwargs["params"]["input_json"])
        self.assertEqual(request["country_code"], "")
        self.assertEqual(rows[0]["name"], "Game 1")
        self.assertEqual(
            [(event.kind, event.fields["phase"]) for event in events],
            [("unit_started", "rendered_chart"), ("unit_completed", "rendered_chart"),
             ("unit_started", "complete_chart"), ("unit_completed", "complete_chart")],
        )

    def test_comparison_pass_fail_error_and_atomic_sidecar(self):
        expected = [ChartIdentity(rank, 1000 + rank) for rank in range(1, 101)]
        fetcher = lambda week: (ValidateEntries.CHART_URL.format(date=week), expected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_bytes((FIXTURES / "weekly_top100.csv").read_bytes())
            original = path.read_bytes()
            passed, report = ValidateEntries.validate_csv(path, fetcher=fetcher)
            self.assertEqual(passed.status, ValidationStatus.PASSED)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(json.loads(report.read_text())["csv_sha256"], hashlib.sha256(original).hexdigest())

            mismatch = self._csv(
                directory,
                [(1, 1002), (2, 1001)] + [(row.rank, row.appid) for row in expected[2:]],
                name="mismatch.csv",
            )
            failed, _ = ValidateEntries.validate_csv(mismatch, fetcher=fetcher)
            self.assertEqual(failed.status, ValidationStatus.FAILED)
            self.assertEqual(len(failed.weekly.wrong_ranks), 2)

            error, error_report = ValidateEntries.validate_csv(
                path, fetcher=lambda week: (_ for _ in ()).throw(RuntimeError("offline"))
            )
            self.assertEqual(error.status, ValidationStatus.ERROR)
            self.assertEqual(json.loads(error_report.read_text())["weekly"]["error"], "offline")

    def test_cli_exit_codes_and_paths_without_network(self):
        result = Mock(status=ValidationStatus.FAILED)
        result.weekly.week = "2026-08-04"
        with patch.object(
            ValidateEntries,
            "run_validation",
            return_value=(result, Path("failed.csv"), Path("failed.validation.json")),
        ):
            self.assertEqual(ValidateEntries.main(["input.csv"]), ValidateEntries.EXIT_FAILED)

    def test_artifacts_are_classified_together_for_pass_fail_and_error(self):
        expected = [ChartIdentity(rank, 1000 + rank) for rank in range(1, 101)]
        passing_fetcher = lambda week: (ValidateEntries.CHART_URL.format(date=week), expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(workflow_paths, "CSV_DIR", root / "CSV"), patch.object(
                workflow_paths, "CSV_ERROR_DIR", root / "CSV_error"
            ):
                passed_input = self._csv(root, [(item.rank, item.appid) for item in expected], name="pass.csv")
                result, csv_path, report_path = ValidateEntries.run_validation(
                    passed_input, fetcher=passing_fetcher
                )
                self.assertEqual(result.status, ValidationStatus.PASSED)
                self.assertEqual(csv_path.parent, root / "CSV")
                self.assertEqual(report_path.parent, csv_path.parent)

                failed_input = self._csv(
                    root, [(1, 9999)] + [(item.rank, item.appid) for item in expected[1:]], name="fail.csv"
                )
                result, csv_path, report_path = ValidateEntries.run_validation(
                    failed_input, fetcher=passing_fetcher
                )
                self.assertEqual(result.status, ValidationStatus.FAILED)
                self.assertEqual(csv_path.parent, root / "CSV_error")
                self.assertEqual(report_path.parent, csv_path.parent)

                error_input = self._csv(root, [(item.rank, item.appid) for item in expected], name="error.csv")
                result, csv_path, report_path = ValidateEntries.run_validation(
                    error_input,
                    fetcher=lambda week: (_ for _ in ()).throw(RuntimeError("offline")),
                )
                self.assertEqual(result.status, ValidationStatus.ERROR)
                self.assertEqual(csv_path.parent, root / "CSV_error")
                self.assertEqual(report_path.parent, csv_path.parent)


if __name__ == "__main__":
    unittest.main()
