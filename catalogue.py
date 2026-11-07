"""Bounded discovery of Vodafone's public product sitemap and exact variants."""
from urllib.parse import urlsplit
from xml.etree import ElementTree
from product_pages import ProductScripts, same_url


def parse_variants(html, store, path, money):
    parser = ProductScripts()
    parser.feed(html)
    groups = []
    for doc in parser.documents:
        nodes = doc if isinstance(doc, list) else doc.get('@graph', [doc])
        groups.extend(n for n in nodes if isinstance(n, dict) and n.get('@type') == 'ProductGroup'
                      and same_url(n.get('url', ''), 'https://' + store['host'] + path))
    if len(groups) != 1:
        raise ValueError('Exact product group missing')
    group = groups[0]
    seller = group.get('offers', {}).get('seller', {}).get('name')
    if seller != 'Vodafone Egypt E-Shop':
        raise ValueError('Unverified seller')
    items = []
    for variant in group.get('hasVariant', []):
        offer = variant.get('offers', {})
        sku = str(variant.get('sku') or '')
        url = offer.get('url', '')
        if not sku or offer.get('@type') != 'Offer' or offer.get('priceCurrency') != 'EGP':
            raise ValueError('Incomplete variant offer')
        if urlsplit(url).hostname != store['host'] or urlsplit(url).path != path:
            raise ValueError('Variant URL mismatch')
        stock = offer.get('availability', '').rsplit('/', 1)[-1]
        if stock not in ('InStock', 'OutOfStock', 'SoldOut'):
            raise ValueError('Unknown stock')
        items.append({'key': f"{store['id']}:{sku}:{urlsplit(url).query}",
                      'store': store['id'], 'name': variant['name'][:180],
                      'variant': variant['name'][:100], 'sku': sku,
                      'price': money(offer['price']), 'available': stock == 'InStock',
                      'currency': 'EGP', 'url': url, 'source_path': path, 'seller': seller})
    if not items:
        raise ValueError('No exact variants')
    return items


def collect_catalogue(store, client, money):
    root = ElementTree.fromstring(client.get('/sitemap-en.xml').lstrip('\ufeff'))
    paths = sorted({urlsplit(n.text).path for n in root.iter()
                    if n.tag.endswith('}loc') and n.text
                    and urlsplit(n.text).hostname == store['host']
                    and urlsplit(n.text).path.startswith('/en/prod/')})
    if not paths:
        raise ValueError('Empty product sitemap')
    cursor = store.get('_cursor', 0) % len(paths)
    count = min(store.get('batch_size', 12), len(paths))
    selected = [paths[(cursor + i) % len(paths)] for i in range(count)]
    selected = list(dict.fromkeys(store.get('pinned_paths', []) + selected))
    items, errors = [], []
    for path in selected:
        try:
            items.extend(parse_variants(client.get(path), store, path, money))
        except Exception as exc:
            errors.append({'path': path, 'error': str(exc)[:120]})
    store['_scan'] = {'catalogue_products': len(paths), 'pages_checked': len(selected),
                      'next_cursor': (cursor + count) % len(paths), 'page_errors': errors}
    if not items:
        raise ValueError('No verified catalogue variants')
    return items


def confirm_catalogue(item, store, client, money):
    # Query variants are disallowed by robots.txt. Re-read the allowed base page;
    # its explicit hasVariant offers contain the exact SKU/color being checked.
    return any(v['key'] == item['key'] and v['price'] == item['price'] and v['available']
               for v in parse_variants(client.get(item['source_path']), store,
                                       item['source_path'], money))
