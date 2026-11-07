"""Strict single-product JSON-LD adapter; never use category/recommendation prices."""
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote


class ProductScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = dict(attrs).get('type', '').lower() == 'application/ld+json'
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.documents.append(json.loads(''.join(self.parts)))
            self.active = False


def same_url(a, b):
    a, b = urlsplit(a), urlsplit(b)
    return a.scheme == b.scheme == 'https' and a.hostname == b.hostname and unquote(a.path).rstrip('/') == unquote(b.path).rstrip('/') and a.query == b.query


def parse_product(html, store, target, money):
    parser = ProductScripts()
    parser.feed(html)
    nodes = []
    for document in parser.documents:
        if isinstance(document, list):
            nodes.extend(document)
        elif isinstance(document, dict):
            nodes.extend(document.get('@graph', [document]))
    url = 'https://' + store['host'] + target['path']
    matches = []
    for node in nodes:
        if not isinstance(node, dict) or node.get('@type') != 'Product':
            continue
        if target['model'].casefold() not in node.get('name', '').casefold():
            continue
        if target.get('sku') and str(node.get('sku')) != target['sku']:
            continue
        offers = node.get('offers', [])
        offers = offers if isinstance(offers, list) else [offers]
        if len(offers) != 1 or offers[0].get('@type') != 'Offer':
            continue
        offer = offers[0]
        if not same_url(node.get('url') or offer.get('url', ''), url):
            continue
        if offer.get('priceCurrency') != 'EGP':
            raise ValueError('Product currency is not EGP')
        availability = offer.get('availability', '').rsplit('/', 1)[-1]
        if availability not in ('InStock', 'OutOfStock', 'SoldOut'):
            raise ValueError('Unconfirmed stock status')
        seller = offer.get('seller', {})
        seller = seller.get('name', '') if isinstance(seller, dict) else str(seller)
        matches.append({
            'key': f"{store['id']}:{target['id']}:{seller or 'unspecified-seller'}",
            'store': store['id'], 'name': node['name'][:180],
            'variant': target.get('variant', 'Adapter only'), 'sku': str(node.get('sku') or target['model']),
            'price': money(offer['price']), 'available': availability == 'InStock',
            'currency': 'EGP', 'url': url, 'target_id': target['id'],
            'seller': seller or 'غير مؤكد آليًا؛ راجع البائع والضمان في صفحة الشراء',
            'notify_restock': target.get('notify_restock', False),
        })
    if len(matches) != 1:
        raise ValueError('Exact single-product offer not found; no substitute price accepted')
    return matches[0]


def collect_pages(store, client, money):
    return [parse_product(client.get(t['path']), store, t, money) for t in store['targets']]


def confirm_page(item, store, client, money):
    target = next(t for t in store['targets'] if t['id'] == item['target_id'])
    again = parse_product(client.get(target['path']), store, target, money)
    return again['key'] == item['key'] and again['price'] == item['price'] and again['available']
