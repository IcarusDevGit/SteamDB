"""Test extraction/update CLI contracts and atomic database boundaries."""

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
    """Exercise multiweek CLI flow, approval gates, and transaction outcomes."""
    def test_cli_accepts_optional_range_boundaries_and_rejects_invalid_input(self):
        parser = main.build_parser()
        defaults = parser.parse_args([])
        self.assertIsNone(defaults.start_date)
        self.assertIsNone(defaults.end_date)
        single = parser.parse_args(["2026-08-04"])
        self.assertEqual((single.start_date, single.end_date), ("2026-08-04", None))
        ranged = parser.parse_args(["2026-08-04", "2026-08-25"])
        self.assertEqual(
            (ranged.start_date, ranged.end_date),
            ("2026-08-04", "2026-08-25"),
        )
        with self.assertRaises(SystemExit):
            parser.parse_args(["2026-08-05"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["not-a-date"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["2026-08-04", "2026-08-11", "2026-08-18"])

    def test_select_dates_defaults_single_range_equal_and_reversed(self):
        self.assertEqual(
            main.select_dates(None, None, now=main.datetime(2026, 8, 28, tzinfo=main.timezone.utc)),
            ["2026-08-25"],
        )
        self.assertEqual(main.select_dates("2026-08-04"), ["2026-08-04"])
        self.assertEqual(
            main.select_dates("2026-08-04", "2026-08-25"),
            ["2026-08-04", "2026-08-11", "2026-08-18", "2026-08-25"],
        )
        self.assertEqual(
            main.select_dates("2026-08-04", "2026-08-04"),
            ["2026-08-04"],
        )
        with self.assertRaisesRegex(ValueError, "end date must not precede start date"):
            main.select_dates("2026-08-11", "2026-08-04")
        with self.assertRaisesRegex(ValueError, "end date requires a start date"):
            main.select_dates(None, "2026-08-04")

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

    def test_equal_range_uses_single_week_output_file(self):
        async def extractor(dates, config=None):
            week = dates[0]
            return [{"week_date": week, "rank": 1, "appid": 10, "name": "Game"}]

        def validator(path):
            return Mock(status=ValidationStatus.PASSED), Path(path), Path(path).with_suffix(".json")

        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            output = Path(directory) / "one.csv"
            code = main.main(
                ["2026-08-04", "2026-08-04", "--output", str(output)],
                extractor=extractor,
                validator=validator,
            )
            output_exists = output.exists()
        self.assertEqual(code, 0)
        self.assertTrue(output_exists)

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
                ["2026-08-04", "2026-08-18", "--output", directory],
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

    def test_apply_csv_parser_path_is_optional(self):
        parser = UpdateDB.build_parser()
        batch = parser.parse_args(["apply", "csv", "--approved"])
        self.assertIsNone(batch.csv)
        explicit = parser.parse_args(["apply", "csv", "review.csv", "--approved"])
        self.assertEqual(explicit.csv, Path("review.csv"))

    def test_default_selection_is_nonrecursive_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.csv").touch()
            (root / "A.csv").touch()
            (root / "notes.txt").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "ignored.csv").touch()
            self.assertEqual(
                [path.name for path in apply_validated_csv.discover_csvs(root)],
                ["A.csv", "b.csv"],
            )

    def test_batch_rejects_override_and_empty_directory_before_mutation(self):
        database = Mock()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "explicit CSV"):
                UpdateDB.dispatch(
                    ["apply", "csv", "--approved", "--validation-report", "one.json"],
                    dependencies={"database": database, "csv_directory": Path(directory)},
                )
            with self.assertRaisesRegex(ValueError, "no CSV files"):
                UpdateDB.dispatch(
                    ["apply", "csv", "--approved"],
                    dependencies={"database": database, "csv_directory": Path(directory)},
                )
        database.apply_validated_records.assert_not_called()

    def test_explicit_success_archives_exact_csv_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            archive = root / "CSV upserted"
            source.mkdir()
            path = self._csv(source)
            report = path.with_name(f"{path.stem}.validation.json")
            database = Mock()
            database.apply_validated_records.return_value = 1
            with patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive):
                result = UpdateDB.dispatch(
                    ["apply", "csv", str(path), "--approved"],
                    dependencies={"database": database},
                )
            self.assertEqual((result.applied, result.failed), (1, 0))
            self.assertFalse(path.exists())
            self.assertFalse(report.exists())
            self.assertTrue((archive / path.name).exists())
            self.assertTrue((archive / report.name).exists())

    def test_explicit_report_override_is_the_report_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive = root / "source", root / "CSV upserted"
            source.mkdir()
            path = self._csv(source)
            adjacent = path.with_name(f"{path.stem}.validation.json")
            explicit = source / "operator-evidence.json"
            adjacent.replace(explicit)
            database = Mock()
            database.apply_validated_records.return_value = 1
            with patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive):
                UpdateDB.dispatch(
                    [
                        "apply", "csv", str(path), "--approved",
                        "--validation-report", str(explicit),
                    ],
                    dependencies={"database": database},
                )
            self.assertTrue((archive / path.name).exists())
            self.assertTrue((archive / explicit.name).exists())
            self.assertFalse((archive / adjacent.name).exists())

    def test_batch_continues_quarantines_failure_and_reports_mixed_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, errors = root / "CSV", root / "CSV upserted", root / "CSV_error"
            source.mkdir()
            first = self._csv(source, name="01-good.csv")
            failed = self._csv(source, unresolved="Mystery", name="02-bad.csv")
            last = self._csv(source, name="03-good.csv", week="2026-08-11")
            failed_report = failed.with_name(f"{failed.stem}.validation.json")
            database = Mock()
            database.apply_validated_records.return_value = 1
            events = []
            with (
                patch.object(apply_validated_csv.workflow_paths, "CSV_DIR", source),
                patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive),
                patch.object(apply_validated_csv.workflow_paths, "CSV_ERROR_DIR", errors),
            ):
                result = UpdateDB.dispatch(
                    ["apply", "csv", "--approved"],
                    dependencies={"database": database, "reporter": events.append},
                )
            self.assertEqual((result.applied, result.failed, result.exit_code), (2, 1, 1))
            self.assertEqual(database.apply_validated_records.call_count, 2)
            self.assertTrue((archive / first.name).exists())
            self.assertTrue((archive / last.name).exists())
            self.assertFalse(failed.exists())
            self.assertFalse(failed_report.exists())
            quarantined_csvs = list(errors.glob("02-bad.*.csv"))
            quarantined_reports = list(errors.glob("02-bad.validation.*.json"))
            error_reports = list(errors.glob("02-bad.*.upsert-error.json"))
            self.assertEqual((len(quarantined_csvs), len(quarantined_reports), len(error_reports)), (1, 1, 1))
            payload = json.loads(error_reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["stage"], "validation")
            self.assertFalse(payload["database_committed"])
            self.assertIn("BATCH files=3 succeeded=2 failed=1 records_applied=2", result.render())
            batch_outcomes = [
                event.fields["outcome"] for event in events
                if event.kind == "candidate_completed"
                and event.fields.get("operation") == "apply_csv_batch"
            ]
            self.assertEqual(batch_outcomes, ["applied", "failed", "applied"])

    def test_batch_archive_collision_is_quarantined_without_database_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, errors = root / "CSV", root / "CSV upserted", root / "CSV_error"
            source.mkdir()
            archive.mkdir()
            path = self._csv(source)
            (archive / path.name).write_text("existing", encoding="utf-8")
            database = Mock()
            with (
                patch.object(apply_validated_csv.workflow_paths, "CSV_DIR", source),
                patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive),
                patch.object(apply_validated_csv.workflow_paths, "CSV_ERROR_DIR", errors),
            ):
                result = UpdateDB.dispatch(
                    ["apply", "csv", "--approved"], dependencies={"database": database}
                )
            self.assertEqual(result.failed, 1)
            database.apply_validated_records.assert_not_called()
            self.assertEqual((archive / path.name).read_text(encoding="utf-8"), "existing")
            self.assertEqual(len(list(errors.glob("approved.*.csv"))), 1)

    def test_batch_continues_when_quarantine_itself_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive = root / "CSV", root / "CSV upserted"
            source.mkdir()
            self._csv(source, unresolved="Mystery", name="01-bad.csv")
            good = self._csv(source, name="02-good.csv")
            database = Mock()
            database.apply_validated_records.return_value = 1
            with (
                patch.object(apply_validated_csv.workflow_paths, "CSV_DIR", source),
                patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive),
                patch.object(apply_validated_csv, "quarantine_failure", side_effect=OSError("disk full")),
            ):
                result = UpdateDB.dispatch(
                    ["apply", "csv", "--approved"], dependencies={"database": database}
                )
            self.assertEqual((result.applied, result.failed), (1, 1))
            self.assertTrue((archive / good.name).exists())
            self.assertIn("QUARANTINE_ERROR", result.render())

    def test_post_commit_archive_failure_is_quarantined_and_batch_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, archive, errors = root / "CSV", root / "CSV upserted", root / "CSV_error"
            source.mkdir()
            failed = self._csv(source, name="01-archive-fails.csv")
            good = self._csv(source, name="02-good.csv", week="2026-08-11")
            database = Mock()
            database.apply_validated_records.return_value = 1
            original_move = apply_validated_csv.shutil.move
            failed_once = {"value": False}

            def move(source_path, destination_path):
                source_value = Path(source_path)
                if source_value == failed and not failed_once["value"]:
                    failed_once["value"] = True
                    raise OSError("archive unavailable")
                return original_move(source_path, destination_path)

            with (
                patch.object(apply_validated_csv.workflow_paths, "CSV_DIR", source),
                patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive),
                patch.object(apply_validated_csv.workflow_paths, "CSV_ERROR_DIR", errors),
                patch.object(apply_validated_csv.shutil, "move", side_effect=move),
            ):
                result = UpdateDB.dispatch(
                    ["apply", "csv", "--approved"], dependencies={"database": database}
                )
            self.assertEqual(database.apply_validated_records.call_count, 2)
            self.assertEqual((result.applied, result.failed), (2, 1))
            self.assertTrue((archive / good.name).exists())
            error_report = next(errors.glob("01-archive-fails.*.upsert-error.json"))
            payload = json.loads(error_report.read_text(encoding="utf-8"))
            self.assertEqual(payload["stage"], "archival")
            self.assertTrue(payload["database_committed"])

    def test_explicit_failure_leaves_artifacts_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._csv(root, unresolved="Mystery")
            report = path.with_name(f"{path.stem}.validation.json")
            with self.assertRaisesRegex(ValueError, "unresolved tags"):
                UpdateDB.dispatch(
                    ["apply", "csv", str(path), "--approved"],
                    dependencies={"database": Mock()},
                )
            self.assertTrue(path.exists())
            self.assertTrue(report.exists())

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
            database = Mock()
            database.apply_validated_records.return_value = 1
            archive = Path(directory) / "archive"
            forms = (
                lambda path: ["apply", "csv", str(path), "--approved"],
                lambda path: [str(path), "--approved"],
                lambda path: ["upsert-csv", "--csv", str(path), "--approved"],
            )
            with patch.object(apply_validated_csv.workflow_paths, "CSV_UPSERTED_DIR", archive):
                for index, form in enumerate(forms):
                    path = self._csv(directory, name=f"approved-{index}.csv")
                    result = UpdateDB.dispatch(form(path), dependencies={"database": database})
                    self.assertEqual(result.applied, 1)
            self.assertEqual(database.apply_validated_records.call_count, 3)


if __name__ == "__main__":
    unittest.main()
