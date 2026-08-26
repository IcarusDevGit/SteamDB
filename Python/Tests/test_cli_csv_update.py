import csv
import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import UpdateDB
import WriteCSV
import db
import main
from database_updates import apply_validated_csv
from workflow_models import BranchState, ExtractionRecord
from validation_models import ValidationStatus


class CliCsvUpdateTests(unittest.TestCase):
    def test_cli_accepts_multiple_tuesdays_and_rejects_other_days(self):
        parser = main.build_parser()
        args = parser.parse_args(["2026-08-04", "2026-08-11"])
        self.assertEqual(args.dates, ["2026-08-04", "2026-08-11"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["2026-08-05"])

    def test_csv_round_trip_preserves_week_and_optional_zero(self):
        record = ExtractionRecord("2026-08-04", 1, 10, "Game", rating=0.0, price=0.0, discount=0)
        record.itad_state = BranchState.SUCCEEDED
        record.rating_state = BranchState.SUCCEEDED
        record.steam_html_state = BranchState.SKIPPED
        with tempfile.TemporaryDirectory() as directory:
            path = WriteCSV.write_csv([record], Path(directory) / "output.csv")
            row = WriteCSV.read_csv(path)[0]
        self.assertEqual(row["week_date"], "2026-08-04")
        self.assertEqual(row["price"], "0.0")
        self.assertEqual(row["discount"], "0")

    def test_main_writes_and_validates_each_week_independently(self):
        calls = []

        async def extractor(dates, config=None):
            week = dates[0]
            calls.append(("extract", week))
            return [{"week_date": week, "rank": 1, "appid": 10, "name": "Game"}]

        def validator(path):
            week = WriteCSV.read_csv(path)[0]["week_date"]
            calls.append(("validate", week))
            result = Mock(status=ValidationStatus.PASSED)
            return result, Path(path), Path(path).with_suffix(".validation.json")

        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            code = main.main(
                ["2026-08-04", "2026-08-11", "--output", directory],
                extractor=extractor,
                validator=validator,
            )
            csvs = sorted(Path(directory).glob("*.csv"))
        self.assertEqual(code, 0)
        self.assertEqual(len(csvs), 2)
        self.assertEqual(
            calls,
            [
                ("extract", "2026-08-04"), ("validate", "2026-08-04"),
                ("extract", "2026-08-11"), ("validate", "2026-08-11"),
            ],
        )

    def test_main_mixed_outcome_and_later_extraction_error_preserve_earlier_csv(self):
        async def extractor(dates, config=None):
            week = dates[0]
            if week == "2026-08-18":
                raise RuntimeError("weekly fetch failed")
            return [{"week_date": week, "rank": 1, "appid": 10, "name": "Game"}]

        def validator(path):
            week = WriteCSV.read_csv(path)[0]["week_date"]
            status = ValidationStatus.PASSED if week == "2026-08-04" else ValidationStatus.FAILED
            return Mock(status=status), Path(path), Path(path).with_suffix(".validation.json")

        stdout, stderr = StringIO(), StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stdout), redirect_stderr(stderr):
            code = main.main(
                ["2026-08-04", "2026-08-11", "2026-08-18", "--output", directory],
                extractor=extractor,
                validator=validator,
            )
            csvs = sorted(Path(directory).glob("*.csv"))
        self.assertEqual(code, 1)
        self.assertEqual(len(csvs), 2)
        self.assertIn("status=passed", stdout.getvalue())
        self.assertIn("status=failed", stdout.getvalue())
        self.assertIn("2026-08-18", stderr.getvalue())

    def test_unresolved_summary_is_sorted_and_artifact_specific(self):
        records = [
            {"name": "Second", "appid": 20, "rank": 2, "unresolved_tags": ["zeta", "Alpha"]},
            {"name": "First", "appid": 10, "rank": 1, "unresolved_tags": ["alpha"]},
        ]
        output = StringIO()
        with redirect_stdout(output):
            main.print_unresolved_summary(records, Path("review.csv"))
        rendered = output.getvalue()
        self.assertIn("unresolved_tags=2", rendered)
        self.assertLess(rendered.index("unresolved_tag=Alpha"), rendered.index("unresolved_tag=zeta"))
        self.assertIn('resolve tags "review.csv"', rendered)

    def _csv(self, directory, unresolved="", *, name="approved.csv", week="2026-08-04"):
        path = Path(directory) / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=WriteCSV.FIELDNAMES)
            writer.writeheader()
            writer.writerow({
                "week_date": week, "rank": "1", "appid": "10", "name": "Game",
                "tags": "Action", "tag_ids": "1", "unresolved_tags": unresolved,
                "rating": "0.8", "price": "9.99", "discount": "20",
                "last_week_rank": "2", "consecutive_weeks": "3", "errors": "",
            })
        self._report(path, week=week)
        return path

    def _report(self, path, *, week="2026-08-04", status="passed", report_path=None):
        report = report_path or path.with_name(f"{path.stem}.validation.json")
        report.write_text(
            json.dumps({
                "schema_version": 1,
                "status": status,
                "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "weekly": {"week": week},
            }),
            encoding="utf-8",
        )
        return report

    def test_update_requires_approval_and_rejects_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            with self.assertRaises(PermissionError):
                UpdateDB.apply_csv(path)
            unresolved = self._csv(directory, "Mystery")
            with self.assertRaises(ValueError):
                UpdateDB.apply_csv(unresolved, approved=True)

    def test_approved_rows_delegate_once_to_database_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            with patch.object(apply_validated_csv.db, "apply_validated_records", return_value=1) as apply:
                self.assertEqual(UpdateDB.apply_csv(path, approved=True), 1)
                apply.assert_called_once()

    def test_chart_gate_rejects_missing_failed_stale_wrong_week_and_multiweek(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            database = Mock()
            report = path.with_name(f"{path.stem}.validation.json")
            report.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                apply_validated_csv.apply_csv(path, approved=True, database=database)
            self._report(path, status="failed")
            with self.assertRaisesRegex(ValueError, "must be passed"):
                apply_validated_csv.apply_csv(path, approved=True, database=database)
            self._report(path)
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest"):
                apply_validated_csv.apply_csv(path, approved=True, database=database)
            self._report(path, week="2026-08-11")
            with self.assertRaisesRegex(ValueError, "does not cover"):
                apply_validated_csv.apply_csv(path, approved=True, database=database)

            multi = self._csv(directory, name="multi.csv")
            with multi.open("a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow([
                    "2026-08-11", "2", "20", "Other", "Action", "1", "", "0.8",
                    "9.99", "20", "2", "3", "",
                ])
            self._report(multi)
            with self.assertRaisesRegex(ValueError, "exactly one"):
                apply_validated_csv.apply_csv(multi, approved=True, database=database)
            database.apply_validated_records.assert_not_called()

    def test_explicit_validation_report_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            adjacent = path.with_name(f"{path.stem}.validation.json")
            explicit = Path(directory) / "evidence.json"
            adjacent.replace(explicit)
            database = Mock()
            database.apply_validated_records.return_value = 1
            self.assertEqual(
                apply_validated_csv.apply_csv(
                    path, approved=True, report_path=explicit, database=database
                ),
                1,
            )
            args = UpdateDB.build_parser().parse_args(
                ["apply", "csv", str(path), "--approved", "--validation-report", str(explicit)]
            )
            self.assertEqual(args.validation_report, explicit)

    def test_database_boundary_commits_atomic_upserts(self):
        class Cursor:
            def __init__(self): self.calls = []
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, statement, params): self.calls.append((statement, params))

        class Connection:
            def __init__(self):
                self.cursor_value = Cursor()
                self.committed = self.rolled_back = self.closed = False
            def cursor(self): return self.cursor_value
            def commit(self): self.committed = True
            def rollback(self): self.rolled_back = True
            def close(self): self.closed = True

        connection = Connection()
        record = {
            "week_date": "2026-08-04", "rank": 1, "appid": 10, "name": "Game",
            "tag_ids": [1], "tag_names": ["Action"], "price": 9.99,
            "discount": 20, "rating": 0.8, "last_week_rank": 2, "consecutive_weeks": 3,
        }
        second = {
            **record, "rank": 2, "appid": 20, "name": "Other",
            "tag_ids": [1, 2], "tag_names": ["Action", "Strategy"],
        }
        bulk_calls = []

        def bulk(cursor, statement, values, page_size):
            bulk_calls.append((statement, values, page_size))

        with (
            patch.object(db, "get_connection", return_value=connection),
            patch.object(db, "execute_values", side_effect=bulk),
        ):
            self.assertEqual(db.apply_validated_records([record, second]), 2)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.cursor_value.calls), 1)
        self.assertEqual(len(bulk_calls), 3)
        tag_statement, tag_values, tag_page_size = bulk_calls[0]
        game_statement, game_values, game_page_size = bulk_calls[1]
        weeksheet_statement, weeksheet_values, weeksheet_page_size = bulk_calls[2]
        self.assertIn("ON CONFLICT (id) DO NOTHING", tag_statement)
        self.assertIn("ON CONFLICT (id) DO NOTHING", game_statement)
        self.assertNotIn("DO UPDATE", tag_statement)
        self.assertNotIn("DO UPDATE", game_statement)
        self.assertIn("ON CONFLICT (week_date, game_id) DO UPDATE", weeksheet_statement)
        self.assertEqual(tag_values, [(1, "Action"), (2, "Strategy")])
        self.assertEqual(tag_page_size, 2)
        self.assertEqual([value[2] for value in game_values], [[1], [1, 2]])
        self.assertEqual(game_page_size, 2)
        self.assertEqual(len(weeksheet_values), 2)
        self.assertEqual(weeksheet_page_size, 2)

    def test_contradictory_tag_mapping_fails_before_connection(self):
        records = [
            {"appid": 10, "tag_ids": [1], "tag_names": ["Action"]},
            {"appid": 20, "tag_ids": [1], "tag_names": ["Strategy"]},
        ]
        with (
            patch.object(db, "get_connection") as connection,
            self.assertRaisesRegex(ValueError, "tag id 1.*Action.*Strategy"),
        ):
            db.apply_validated_records(records)
        connection.assert_not_called()

    def test_bulk_failure_rolls_back_and_closes_connection(self):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, statement, params): pass

        class Connection:
            def __init__(self):
                self.committed = self.rolled_back = self.closed = False
            def cursor(self): return Cursor()
            def commit(self): self.committed = True
            def rollback(self): self.rolled_back = True
            def close(self): self.closed = True

        connection = Connection()
        record = {
            "week_date": "2026-08-04", "rank": 1, "appid": 10, "name": "Game",
            "tag_ids": [1], "tag_names": ["Action"], "price": 9.99,
            "discount": 20, "rating": 0.8, "last_week_rank": 2, "consecutive_weeks": 3,
        }
        with (
            patch.object(db, "get_connection", return_value=connection),
            patch.object(db, "execute_values", side_effect=[None, None, RuntimeError("bulk failed")]),
            self.assertRaisesRegex(RuntimeError, "bulk failed"),
        ):
            db.apply_validated_records([record])
        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)

    def test_new_and_compatibility_cli_paths_delegate_to_same_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._csv(directory)
            database = Mock()
            database.apply_validated_records.return_value = 1
            for argv in (
                ["apply", "csv", str(path), "--approved"],
                [str(path), "--approved"],
                ["upsert-csv", "--csv", str(path), "--approved"],
            ):
                result = UpdateDB.dispatch(argv, dependencies={"database": database})
                self.assertEqual(result.applied, 1)
            self.assertEqual(database.apply_validated_records.call_count, 3)


if __name__ == "__main__":
    unittest.main()
