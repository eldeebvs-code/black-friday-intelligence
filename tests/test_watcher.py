import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import watcher as w


class Prices(unittest.TestCase):
    def setUp(self):
        self.now = w.utcnow()
        self.state = {'version': 1, 'items': {}, 'sent': {}}
        self.store = {'id': 'test', 'host': 'example.com', 'pages': 1}
        self.product = {'id': 1, 'handle': 'shoe', 'title': 'Shoe', 'variants': [
            {'id': 2, 'title': 'Black / 40', 'price': '1000', 'available': True, 'sku': 'shoe-40'},
            {'id': 3, 'title': 'Black / 41', 'price': '1200', 'available': False, 'sku': 'shoe-41'}]}
        self.item = w.variants(self.store, self.product)[0]

    def baseline(self):
        w.observe(self.state, self.item, self.now - timedelta(hours=1))

    def drop(self, price='800'):
        return dict(self.item, price=w.money(price))

    def test_first_observation_is_not_discount(self):
        self.assertIsNone(w.observe(self.state, self.item, self.now))

    def test_historical_drop(self):
        self.baseline()
        event = w.observe(self.state, self.drop(), self.now)
        self.assertEqual(event['baseline'], '1000.00')

    def test_exact_threshold(self):
        self.baseline()
        self.assertIsNone(w.observe(self.state, self.drop('850.01'), self.now))
        self.assertIsNotNone(w.observe(self.state, self.drop('850'), self.now))

    def test_stock_required(self):
        self.baseline()
        self.assertIsNone(w.observe(self.state, dict(self.drop(), available=False), self.now))

    def test_separate_sizes(self):
        self.baseline()
        other = dict(self.drop(), key='test:1:3')
        self.assertIsNone(w.observe(self.state, other, self.now))

    def test_no_inflated_reference(self):
        self.baseline()
        w.observe(self.state, self.drop('2000'), self.now - timedelta(minutes=30))
        self.assertIsNone(w.observe(self.state, self.drop('1100'), self.now))

    def test_pending_retries_without_secrets_or_delivery(self):
        self.baseline()
        item = self.drop()
        first = w.observe(self.state, item, self.now)
        again = w.observe(self.state, item, self.now + timedelta(minutes=15))
        self.assertEqual(first, again)

    def test_success_deduplicated_across_restarts(self):
        self.baseline()
        item = self.drop()
        w.observe(self.state, item, self.now)
        self.state['sent'][w.event_id(item)] = w.stamp(self.now)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            w.save(path, self.state)
            restored = w.load_state(path)
            self.assertIsNone(w.observe(restored, item, self.now + timedelta(minutes=15)))

    def test_pending_cancelled_on_price_rebound(self):
        self.baseline()
        w.observe(self.state, self.drop(), self.now)
        self.assertIsNone(w.observe(self.state, self.item, self.now + timedelta(minutes=15)))

    def test_pending_expires(self):
        self.baseline()
        w.observe(self.state, self.drop(), self.now)
        self.assertIsNone(w.observe(self.state, self.drop(), self.now + timedelta(hours=7)))

    def test_old_history_not_used(self):
        w.observe(self.state, self.item, self.now - timedelta(days=31))
        self.assertIsNone(w.observe(self.state, self.drop(), self.now))

    def test_change_and_daily_checkpoints(self):
        self.baseline()
        w.observe(self.state, self.item, self.now)
        self.assertEqual(len(self.state['items'][self.item['key']]['history']), 1)
        w.observe(self.state, self.item, self.now + timedelta(days=1))
        self.assertEqual(len(self.state['items'][self.item['key']]['history']), 2)

    def test_price_validation(self):
        for bad in ('NaN', 'Infinity', '-1', '0', 'not a number'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                w.money(bad)
        self.assertEqual(w.money(12345, cents=True), '123.45')

    def test_confirm_exact_variant(self):
        product = copy.deepcopy(self.product)
        product['variants'][0]['price'] = 100000
        product['variants'][1]['price'] = 120000
        class Fake:
            def json(self, path):
                return product
        self.assertTrue(w.confirm(self.item, self.store, Fake()))
        self.assertFalse(w.confirm(self.drop(), self.store, Fake()))
        product['variants'][0]['available'] = False
        self.assertFalse(w.confirm(self.item, self.store, Fake()))

    def test_currency_mismatch(self):
        class Fake:
            def get(self, path):
                return 'Shopify.currency = {"active":"USD"};'
        with self.assertRaises(ValueError):
            w.collect(self.store, Fake())

    def test_collect_and_pinned_cents(self):
        product = self.product
        class Fake:
            def get(self, path):
                return 'Shopify.currency = {"active":"EGP"};'
            def json(self, path):
                return {'products': [product]}
        self.assertEqual(len(w.collect(self.store, Fake())), 2)

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text('{"items": {}}')
            with self.assertRaises(ValueError):
                w.load_state(path)

    @patch.dict('os.environ', {}, clear=True)
    def test_no_secrets_no_send(self):
        self.assertFalse(w.send_telegram('test'))

    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'SECRET', 'TELEGRAM_CHAT_ID': '123'})
    @patch('watcher.urlopen', side_effect=Exception('https://api.telegram.org/botSECRET/sendMessage'))
    def test_token_never_in_failure(self, mock):
        with self.assertRaises(ValueError) as error:
            w.send_telegram('test')
        self.assertNotIn('SECRET', str(error.exception))

    @patch('watcher.Client')
    @patch('watcher.collect')
    def test_one_failed_provider_does_not_stop_others(self, collect, client):
        collect.side_effect = [ValueError('HTTP 403'), [self.item]]
        with tempfile.TemporaryDirectory() as tmp:
            stores = [dict(self.store, enabled=True), dict(self.store, id='other', enabled=True)]
            code = w.run({'stores': stores}, Path(tmp)/'state.json', Path(tmp)/'status.json')
            self.assertEqual(code, 1)
            self.assertIn(self.item['key'], w.load_state(Path(tmp)/'state.json')['items'])


if __name__ == '__main__':
    unittest.main()
