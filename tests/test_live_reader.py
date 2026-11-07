import unittest
from live_reader import validate_url

class LiveURLTests(unittest.TestCase):
    def test_reject_untrusted_private_and_transaction_urls(self):
        for url in ['http://www.amazon.eg/dp/B0C9QT2J6W/','https://localhost/private','https://www.amazon.eg.evil.example/dp/B0C9QT2J6W/','https://user:pass@www.amazon.eg/dp/B0C9QT2J6W/','https://www.noon.com/egypt-en/checkout/','https://www.noon.com:444/egypt-en/test/N70095444V/p/']:
            with self.subTest(url=url),self.assertRaises(ValueError):validate_url(url)
    def test_product_urls_allowlisted(self):
        store,u=validate_url('https://eshop.orange.eg/en/smart-phones/p/honor-x9e-pro')
        self.assertEqual(store,'orange')
