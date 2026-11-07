import unittest
from browser_sources import cash, amazon_item, noon_item

class BrowserTests(unittest.TestCase):
    def test_price_currency_and_ambiguity(self):
        self.assertEqual(cash('EGP 1,234.50'),'1234.50')
        for value in ['USD 123', 'EGP 100 EGP 200', 'EGP 0', 'EGP -1']:
            with self.subTest(value=value), self.assertRaises(ValueError):cash(value)
    def test_redirect_before_reading_price(self):
        class Page: url='https://www.amazon.eg/dp/B000000000'
        with self.assertRaises(ValueError):amazon_item(Page(),{'asin':'B0C9QT2J6W'})
        with self.assertRaises(ValueError):noon_item(Page(),{'sku':'N70095444V'})
