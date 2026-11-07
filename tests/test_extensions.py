import copy
import json
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import Mock
from catalogue import parse_variants, confirm_catalogue, collect_catalogue
from health import update_health
from robots import Robots
from watcher import money, utcnow


class Extensions(unittest.TestCase):
    def setUp(self):
        self.store = {'id': 'vodafone', 'host': 'eshop.vodafone.com.eg'}
        self.path = '/en/prod/ugreen-gan-fast-charger-45w-usb-c-eu'
        self.html = (Path(__file__).parent/'fixtures/vfcharger.html').read_text()

    def test_real_variant_fixture_separates_colors(self):
        items = parse_variants(self.html, self.store, self.path, money)
        self.assertEqual(len(items), 2)
        self.assertNotEqual(items[0]['key'], items[1]['key'])
        self.assertEqual(items[0]['price'], '750.00')

    def test_reject_wrong_product_and_seller(self):
        with self.assertRaises(ValueError):
            parse_variants(self.html, self.store, '/en/prod/other', money)
        with self.assertRaises(ValueError):
            parse_variants(self.html.replace('Vodafone Egypt E-Shop','Other seller'), self.store, self.path, money)

    def test_single_sku_real_fixture(self):
        html = (Path(__file__).parent/'fixtures/vfrav.html').read_text()
        path = '/en/prod/ravpower-rp-pc1099-pd-pioneer-45w-2-port-wall-charger-black'
        items = parse_variants(html, self.store, path, money)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['sku'], '111113585')
        self.assertEqual(items[0]['price'], '922.00')
        self.assertTrue(items[0]['available'])

    def test_recommendations_never_substitute_for_product(self):
        html = '<script type="application/ld+json">' + json.dumps({
            '@type':'CollectionPage', 'mainEntity':{'@type':'Product',
            'url':'https://eshop.vodafone.com.eg'+self.path}}) + '</script>'
        with self.assertRaises(ValueError):
            parse_variants(html,self.store,self.path,money)

    def test_confirmation_reads_base_page_not_blocked_query(self):
        item = parse_variants(self.html, self.store, self.path, money)[0]
        client = Mock()
        client.get.return_value = self.html
        self.assertTrue(confirm_catalogue(item, self.store, client, money))
        client.get.assert_called_once_with(self.path)
        self.assertFalse(confirm_catalogue(dict(item,price='1.00'),self.store,client,money))

    def test_rotation_and_partial_failure(self):
        client = Mock()
        xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(
            '<url><loc>https://eshop.vodafone.com.eg'+p+'</loc></url>' for p in ['/en/prod/a',self.path]) + '</urlset>'
        client.get.side_effect = [xml, ValueError('unavailable'), self.html]
        store = dict(self.store,batch_size=2)
        self.assertEqual(len(collect_catalogue(store, client, money)),2)
        self.assertEqual(len(store['_scan']['page_errors']),1)

    def test_health_daily_failure_recovery_dedup(self):
        state = {}; now=utcnow(); send=Mock(return_value=True)
        report={'providers':[{'store':'x','status':'ok'}],'errors':[]}
        update_health(state,report,now,send)
        update_health(state,report,now+timedelta(minutes=15),send)
        self.assertEqual(send.call_count,1)
        report['providers'][0]['status']='error'
        update_health(state,report,now+timedelta(minutes=30),send)
        update_health(state,report,now+timedelta(minutes=45),send)
        self.assertEqual(send.call_count,2)
        report['providers'][0]['status']='ok'
        update_health(state,report,now+timedelta(hours=1),send)
        update_health(state,report,now+timedelta(hours=26),send)
        self.assertEqual(send.call_count,4)

    def test_failed_health_delivery_not_acknowledged(self):
        state={}; send=Mock(return_value=False)
        update_health(state,{'providers':[],'errors':[]},utcnow(),send)
        self.assertNotIn('daily_at',state['health'])

    def test_robots_wildcards_and_longest_rule(self):
        robots=Robots('User-agent: *\nAllow: /\nDisallow: /*?*Color=\nDisallow: /private\nAllow: /private/public$')
        self.assertTrue(robots.can_fetch('BlackFridayIntelligence/1.1','https://example.com/en/prod/x'))
        self.assertFalse(robots.can_fetch('BlackFridayIntelligence/1.1','https://example.com/en/prod/x?Color=Black'))
        self.assertTrue(robots.can_fetch('bot','https://example.com/private/public'))
        self.assertFalse(robots.can_fetch('bot','https://example.com/private/public/a'))

    def test_specific_robots_group(self):
        robots=Robots('User-agent: *\nDisallow: /\nUser-agent: mine\nAllow: /')
        self.assertTrue(robots.can_fetch('mine/1','https://example.com/x'))
        self.assertFalse(robots.can_fetch('other/1','https://example.com/x'))
