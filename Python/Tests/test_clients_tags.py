"""Test provider payload parsers and canonical tag-resolution precedence."""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from tag_resolution import merge_category_ids, resolve_tags
from workflow_clients import RealExtractionClients, parse_histogram_rating, parse_store_html, parse_weekly


class ClientAndTagTests(unittest.TestCase):
    """Verify normalization of weekly data, ratings, offers, and tag identities."""
    def test_weekly_parser_normalizes_required_fields(self):
        payload = {"response": {"ranks": [{
            "rank": 1,
            "appid": 10,
            "last_week_rank": 3,
            "consecutive_weeks": 4,
            "item": {
                "name": "Game",
                "content_descriptorids": [2, 2],
                "categories": {"features": [29, 2]},
            },
        }]}}
        row = parse_weekly(payload, "2026-08-04")[0]
        self.assertEqual(row, {
            "week_date": "2026-08-04", "rank": 1, "appid": 10, "name": "Game",
            "last_week_rank": 3, "consecutive_weeks": 4, "category_ids": [2, 29],
        })

    def test_rating_includes_closed_week_and_excludes_next_tuesday(self):
        before = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
        during_week = int(datetime(2026, 8, 10, tzinfo=timezone.utc).timestamp())
        next_tuesday = int(datetime(2026, 8, 11, tzinfo=timezone.utc).timestamp())
        payload = {"results": {"rollups": [
            {"date": before, "recommendations_up": 8, "recommendations_down": 2},
            {"date": during_week, "recommendations_up": 2, "recommendations_down": 0},
            {"date": next_tuesday, "recommendations_up": 0, "recommendations_down": 10},
        ]}}
        self.assertEqual(parse_histogram_rating(payload, "2026-08-04"), 10 / 12)

    def test_store_html_parses_discount_and_tags_once(self):
        html = """
        <a class="app_tag">Action</a><a class="app_tag">Action</a>
        <div id="game_area_purchase"><div class="game_area_purchase_game">
          <div class="discount_block" data-price-final="1599">
            <div class="discount_pct">-60%</div>
          </div>
        </div></div>
        """
        data = parse_store_html(html)
        self.assertEqual((data.price, data.discount, data.tags), (15.99, 60, ["Action"]))

    def test_exceptions_and_unresolved_tags(self):
        result = resolve_tags(
            ["Action", "Rogue-lite", "Mystery"],
            {"Action": 1, "Roguelike": 3959},
            exceptions={"rogue-lite": 3959},
            canonical_by_id={1: "Action", 3959: "Roguelike"},
        )
        self.assertEqual(result.ids, [1, 3959])
        self.assertEqual(result.names, ["Action", "Roguelike"])
        self.assertEqual(result.unresolved, ["Mystery"])

    def test_category_lookup_marks_only_missing_records(self):
        result = merge_category_ids([1, 29, 1], {"Action": 1}, {29: "Co-op"})
        self.assertEqual(result.ids, [1, 29])
        self.assertEqual(result.missing, {29: "Co-op"})

    def test_category_name_reuses_existing_tag_id(self):
        result = merge_category_ids(
            [58],
            {"DualSense Controller Support": 57},
            {58: "DualSense Controller Support"},
        )
        self.assertEqual(result.ids, [57])
        self.assertEqual(result.names, ["DualSense Controller Support"])
        self.assertEqual(result.missing, {})

    def test_game_name_normalizes_application_details_and_unavailable_values(self):
        response = Mock(status_code=200, headers={})
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        client = RealExtractionClients(session)
        cases = (
            ({"10": {"success": True, "data": {"name": "  Portal  "}}}, "Portal"),
            ({"10": {"success": False}}, None),
            ({"10": {"success": True, "data": {}}}, None),
            ({"10": {"success": True, "data": {"name": "   "}}}, None),
            ({"10": []}, None),
        )
        for payload, expected in cases:
            with self.subTest(payload=payload):
                response.json.return_value = payload
                self.assertEqual(client._game_name(10), expected)
        session.get.assert_called_with(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": 10, "cc": "us", "l": "english"}, timeout=20,
        )

    def test_game_name_propagates_provider_failures(self):
        response = Mock(status_code=404, headers={})
        response.raise_for_status.side_effect = RuntimeError("provider failed")
        client = RealExtractionClients(Mock(get=Mock(return_value=response)))
        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            client._game_name(10)


if __name__ == "__main__":
    unittest.main()
