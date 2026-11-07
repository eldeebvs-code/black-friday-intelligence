import json
import unittest
from datetime import timedelta
from product_pages import parse_product
from watcher import money, observe, utcnow, event_id, stamp


class ProductPages(unittest.TestCase):
    def setUp(self):
        self.store = {'id': 'raya', 'host': 'www.rayashop.com'}
        self.target = {'id': 'charger', 'path': '/en/charger', 'model': 'EP-T4511N', 'sku': '123'}
        self.node = {'@type': 'Product', 'name': 'Samsung EP-T4511N', 'sku': '123',
                     'url': 'https://www.rayashop.com/en/charger',
                     'offers': {'@type': 'Offer', 'price': 999, 'priceCurrency': 'EGP',
                                'availability': 'https://schema.org/InStock'}}

    def parse(self, node=None):
        html = '<script type="application/ld+json">' + json.dumps(self.node if node is None else node) + '</script>'
        return parse_product(html, self.store, self.target, money)

    def test_product_and_graph(self):
        self.assertEqual(self.parse()['price'], '999.00')
        self.assertTrue(self.parse({'@graph': [self.node]})['available'])

    def test_no_category_recommendations(self):
        with self.assertRaises(ValueError):
            self.parse({'@type': 'CollectionPage', 'mainEntity': {'item': self.node}})

    def test_mismatch_url_sku_model(self):
        for key, value in [('url', 'https://www.rayashop.com/en/other'), ('sku', '987'), ('name', 'Other charger')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse(dict(self.node, **{key: value}))

    def test_stock_currency_ambiguity(self):
        for key, value in [('priceCurrency', 'USD'), ('availability', '')]:
            node = dict(self.node, offers=dict(self.node['offers'], **{key: value}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse(node)
        with self.assertRaises(ValueError):
            self.parse(dict(self.node, offers=[self.node['offers'], self.node['offers']]))

    def test_out_of_stock_recorded(self):
        self.node['offers']['availability'] = 'https://schema.org/OutOfStock'
        self.assertFalse(self.parse()['available'])

    def test_restock_only_after_seen_unavailable(self):
        now = utcnow()
        state = {'items': {}, 'sent': {}}
        item = dict(self.parse(), notify_restock=True)
        self.assertIsNone(observe(state, item, now))
        observe(state, dict(item, available=False), now + timedelta(minutes=15))
        event = observe(state, item, now + timedelta(minutes=30))
        self.assertEqual(event['kind'], 'restock')
        state['sent'][event_id(item, 'restock')] = stamp(now)
        self.assertIsNone(observe(state, item, now + timedelta(minutes=45)))
