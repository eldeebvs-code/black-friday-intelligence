import unittest
from pathlib import Path
from datetime import timedelta
from jumia import product_items, page_data
from watcher import money, observe, utcnow, event_id, message

class JumiaTests(unittest.TestCase):
    def setUp(self):
        self.html=(Path(__file__).parent/'fixtures/jumia-product.html').read_text()
        self.store={'id':'jumia','host':'www.jumia.com.eg'}
        self.path=page_data(self.html)['products'][0]['url']
    def test_actual_seller_and_variant(self):
        item=product_items(self.html,self.store,self.path,money)[0]
        self.assertEqual(item['price'],'580.00')
        self.assertEqual(item['seller'],'omaryousef11')
        self.assertIn('186425',item['key'])
        self.assertIn('217459945',item['key'])
    def test_redirect_and_wrong_currency_rejected(self):
        for a,b in [('"view": "Product"','"view": "Catalog"'),('"countryCode": "EG"','"countryCode": "KE"'),('"priceCurrency": "EGP"','"priceCurrency": "USD"')]:
            with self.subTest(a=a),self.assertRaises(ValueError):
                product_items(self.html.replace(a,b),self.store,self.path,money)
    def test_seller_identity_mismatch(self):
        with self.assertRaises(ValueError):
            product_items(self.html.replace('"sellerId": 186425','"sellerId": 9'),self.store,self.path,money)
    def test_flash_not_presented_as_historical_drop_and_dedup(self):
        item=product_items(self.html,self.store,self.path,money)[0]
        item['flash_listing']=True
        state={'items':{},'sent':{}};now=utcnow()
        event=observe(state,item,now)
        self.assertEqual(event['kind'],'flash')
        self.assertIn('ليست انخفاضًا مثبتًا',message(item,event))
        state['sent'][event_id(item,'flash')]=now.isoformat()
        self.assertIsNone(observe(state,item,now+timedelta(minutes=15)))
    def test_no_flash_without_membership(self):
        item=product_items(self.html,self.store,self.path,money)[0]
        self.assertIsNone(observe({'items':{},'sent':{}},item,utcnow()))
