import unittest

from FetchPriceFromSteam import parse_price_html


class ParsePriceHtmlTests(unittest.TestCase):
    def test_uses_discounted_price(self):
        html = """
            <div id="game_area_purchase">
              <div class="game_area_purchase_game">
                <div class="discount_block" data-price-final="1599">
                  <div class="discount_pct">-60%</div>
                  <div class="discount_final_price">$15.99</div>
                </div>
              </div>
            </div>
        """
        self.assertEqual(parse_price_html(html), (15.99, 60))

    def test_parses_regular_price(self):
        html = """
            <div class="game_area_purchase_game">
              <div class="game_purchase_price" data-price-final="2999">$29.99</div>
            </div>
        """
        self.assertEqual(parse_price_html(html), (29.99, 0))

    def test_parses_free_to_play(self):
        html = """
            <div class="game_area_purchase_game">
              <div class="game_purchase_price">Free To Play</div>
            </div>
        """
        self.assertEqual(parse_price_html(html), (0.0, 0))

    def test_skips_demo_purchase_block(self):
        html = """
            <div id="game_area_purchase">
              <div class="game_area_purchase_game demo_above_purchase">
                <div class="game_purchase_price">Free Demo</div>
              </div>
              <div class="game_area_purchase_game">
                <div class="game_purchase_price" data-price-final="2499">$24.99</div>
              </div>
            </div>
        """
        self.assertEqual(parse_price_html(html), (24.99, 0))


if __name__ == "__main__":
    unittest.main()
