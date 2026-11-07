"""Public Jumia product data: exact seller and simple SKU, no category prices."""
import json
import re
from urllib.parse import urlsplit
from product_pages import ProductScripts, same_url


def page_data(html):
    match = re.search(r'window\.__STORE__\s*=\s*', html)
    if not match:
        raise ValueError('Jumia product data missing')
    data = json.JSONDecoder().raw_decode(html[match.end():])[0]
    if data.get('countryCode') != 'EG':
        raise ValueError('Not Egypt storefront')
    return data


def product_items(html, store, path, money):
    data = page_data(html)
    if data.get('view') != 'Product':
        raise ValueError('Product redirected to a collection')
    products = [p for p in data.get('products', []) if p.get('url') == path]
    if len(products) != 1:
        raise ValueError('Exact product missing')
    product = products[0]
    parser = ProductScripts(); parser.feed(html)
    nodes = [n for doc in parser.documents for n in (doc.get('@graph', [doc]) if isinstance(doc, dict) else doc)]
    matches = [n for n in nodes if n.get('@type') == 'Product'
               and same_url(n.get('url', ''), 'https://' + store['host'] + path)
               and n.get('sku') == product['sku']]
    if len(matches) != 1:
        raise ValueError('Structured product identity does not agree')
    offer = matches[0].get('offers', {})
    seller = offer.get('seller', {})
    if (offer.get('priceCurrency') != 'EGP' or not seller.get('name')
            or str(seller.get('@id')) != str(product.get('sellerId'))):
        raise ValueError('Currency or seller mismatch')
    items = []
    for v in product.get('simples', []):
        if not v.get('sku') or not isinstance(v.get('isBuyable'), bool):
            raise ValueError('Missing exact variant or stock')
        prices = v.get('prices', {})
        if not prices.get('price', '').startswith('EGP '):
            raise ValueError('Variant currency missing')
        items.append({'key': f"jumia:{seller['@id']}:{v['sku']}", 'store': store['id'],
                      'sku': v['sku'], 'name': product['displayName'][:180],
                      'variant': v.get('name') or 'Listed single option',
                      'price': money(prices['rawPrice']), 'available': v['isBuyable'],
                      'currency': 'EGP', 'seller': seller['name'],
                      'url': 'https://' + store['host'] + path, 'source_path': path})
        discount = prices.get('discount', '')
        if re.fullmatch(r'\d{1,2}%', discount):
            items[-1]['advertised_discount'] = int(discount[:-1])
    if not items:
        raise ValueError('No exact variants')
    return items


def collect_jumia(store, client, money):
    # Listing prices are discovery hints only. Fetch each product to resolve seller.
    listing = page_data(client.get('/flash-sales/'))
    paths = list(dict.fromkeys(p['url'] for p in listing.get('products', [])
                              if re.fullmatch(r'/[a-zA-Z0-9_.-]+\.html', p.get('url', ''))))
    if not paths:
        raise ValueError('No flash-sale product links')
    cursor = store.get('_cursor', 0) % len(paths)
    count = min(store.get('batch_size', 8), len(paths))
    selected = list(dict.fromkeys(store.get('pinned_paths', []) +
                [paths[(cursor+i) % len(paths)] for i in range(count)]))
    items, errors = [], []
    for path in selected:
        try:
            batch = product_items(client.get(path), store, path, money)
            for item in batch:
                item['flash_listing'] = path in paths and store.get('notify_flash', False)
                item['flash_min_percent'] = store.get('flash_min_percent', 50)
            items.extend(batch)
        except Exception as exc:
            errors.append({'path': path, 'error': str(exc)[:120]})
    store['_scan'] = {'catalogue_products': len(paths), 'pages_checked': len(selected),
                      'next_cursor': (cursor+count) % len(paths), 'page_errors': errors}
    if not items:
        raise ValueError('No verified Jumia offers')
    return items


def confirm_jumia(item, store, client, money):
    if item.get('flash_listing'):
        current = page_data(client.get('/flash-sales/'))
        if item['source_path'] not in [p.get('url') for p in current.get('products', [])]:
            return False
    return any(v['key'] == item['key'] and v['price'] == item['price'] and v['available']
               and (not item.get('flash_listing') or v.get('advertised_discount', 0) >= item.get('flash_min_percent', 50))
               for v in product_items(client.get(item['source_path']), store, item['source_path'], money))
