import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import UpdateDB
import WriteCSV
from database_updates import resolve_csv_tags
from validation_models import ValidationStatus
from request_scheduler import ProviderGate, ProviderPolicy


class ResolveCsvTagsTests(unittest.TestCase):
    def make_csv(self, directory, unresolved=" dystopian "):
        path = Path(directory) / "review.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=WriteCSV.FIELDNAMES)
            writer.writeheader()
            writer.writerow({
                "week_date": "2026-08-04", "rank": "1", "appid": "10", "name": "Game",
                "tags": "Action", "tag_ids": "1", "unresolved_tags": unresolved,
                "rating": "0.8", "price": "9.99", "discount": "0", "last_week_rank": "2",
                "consecutive_weeks": "3", "errors": "",
            })
        path.with_name("review.validation.json").write_text(json.dumps({
            "status": "passed", "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "weekly": {"week": "2026-08-04"},
        }), encoding="utf-8")
        return path

    def dependencies(self, directory):
        database = Mock()
        database.load_catalog_snapshot.return_value = {
            "games": {}, "tags_by_name": {"Action": 1, " Dystopian ": 42}
        }
        client = Mock()
        client.tag_list = Mock(side_effect=AssertionError("Steam must not be requested"))
        return database, client, Path(directory) / "Exceptions.json"

    def test_registry_and_dry_run_do_not_write(self):
        args = UpdateDB.build_parser().parse_args(["resolve", "tags", "review.csv"])
        self.assertEqual(args.csv, Path("review.csv"))
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory)
            before = path.read_bytes()
            database, client, exceptions = self.dependencies(directory)
            result = resolve_csv_tags.resolve_csv(
                path, database=database, client=client, exception_file=exceptions
            )
            self.assertEqual(result.proposed, 1)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(exceptions.exists())

    def test_apply_rewrites_and_revalidates_without_database_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory)
            database, client, exceptions = self.dependencies(directory)
            validation = Mock(status=ValidationStatus.PASSED)
            validator = Mock(return_value=(validation, path, path.with_name("review.validation.json")))
            result = resolve_csv_tags.resolve_csv(
                path, apply=True, database=database, client=client,
                exception_file=exceptions, validator=validator,
            )
            row = WriteCSV.read_csv(path)[0]
            self.assertEqual((row["tags"], row["tag_ids"], row["unresolved_tags"]),
                             ("Action, Dystopian", "1,42", ""))
            self.assertEqual(result.exit_code, 0)
            validator.assert_called_once()
            database.apply_validated_records.assert_not_called()

    def test_explicit_mapping_validation(self):
        with self.assertRaises(ValueError):
            resolve_csv_tags.parse_explicit_mappings(["Bad"])
        with self.assertRaises(ValueError):
            resolve_csv_tags.parse_explicit_mappings(["Bad=0"])
        with self.assertRaises(ValueError):
            resolve_csv_tags.parse_explicit_mappings(["Bad=2", "bad=2"])

    def test_multiple_names_use_one_steam_tag_list_request(self):
        class Client:
            def __init__(self): self.calls = 0
            async def tag_list(self):
                self.calls += 1
                return [{"id": 42, "name": "Dystopian"}, {"id": 43, "name": "Mystery"}]

        with tempfile.TemporaryDirectory() as directory:
            path = self.make_csv(directory, "Dystopian, mystery")
            database = Mock()
            database.load_catalog_snapshot.return_value = {"games": {}, "tags_by_name": {}}
            client = Client()
            result = resolve_csv_tags.resolve_csv(
                path, database=database, client=client,
                exception_file=Path(directory) / "Exceptions.json",
                gate=ProviderGate(ProviderPolicy(0, 1, 1, retries=0)),
            )
            self.assertEqual(result.proposed, 2)
            self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
