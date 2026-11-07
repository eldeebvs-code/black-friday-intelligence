"""Visible-page parsers for a local Chrome session, with no login/checkout actions."""
import re
from urllib.parse import urlsplit, parse_qs
from watcher import money


def cash(text):
    match = re.fullmatch(r'\s*EGP\s*([\d,]+(?:\.\d{1,2})?)\s*', text.replace('\xa0',' '))
    if not match:
        raise ValueError('Ambiguous price or currency')
    return money(match[1].replace(',',''))


def amazon_item(page, target):
    asin = target['asin']
    if not re.fullmatch(r'[A-Z0-9]{10}', asin) or '/dp/'+asin not in urlsplit(page.url).path:
        raise ValueError('Amazon product identity changed')
    title = page.locator('#productTitle').inner_text(timeout=20000).strip()
    if target.get('model') and target['model'].lower() not in title.lower():
        raise ValueError('Requested model missing')
    prices = page.locator('#corePrice_feature_div .apex-pricetopay-value .a-offscreen').all_text_contents()
    values = {cash(p) for p in prices}
    if len(values) != 1:
        raise ValueError('No unambiguous current purchase price')
    merchant = page.locator('#merchantInfoFeature_feature_div #sellerProfileTriggerId').first
    seller = merchant.inner_text(timeout=5000).strip()
    seller_id = parse_qs(urlsplit(merchant.get_attribute('href') or '').query).get('seller',[''])[0]
    if not seller_id or not seller:
        raise ValueError('Seller not identified')
    available = page.get_by_role('button',name='Add to cart',exact=True).first.is_visible()
    if available:
        available = page.get_by_role('button',name='Add to cart',exact=True).first.is_enabled()
    # An absent buy button is not treated as a proved out-of-stock observation.
    if not available:
        raise ValueError('Purchase availability not confirmed')
    return {'key':f'amazon:{asin}:{seller_id}', 'store':'amazon', 'name':title[:180],
            'variant':target.get('description','Exact ASIN'), 'sku':asin,
            'price':values.pop(),'currency':'EGP','available':True,'seller':seller,
            'url':target['url'],'target':target}


def noon_item(page, target):
    sku=target['sku']
    if '/'+sku+'/p/' not in urlsplit(page.url).path:
        raise ValueError('Noon product identity changed')
    title=page.locator('[data-qa="pdp-product-name"]').inner_text(timeout=25000).strip()
    price=cash(page.locator('[data-qa="pdp-product-name"]').locator('..').locator('[data-qa="div-price-now"]').inner_text())
    seller=page.get_by_role('link',name=re.compile('^Sold by '))
    href=seller.get_attribute('href') or ''
    seller_id=re.search(r'/seller/(p-\d+)/',href)
    query=parse_qs(urlsplit(href).query)
    if not seller_id or query.get('sku') != [sku] or not query.get('offer_code'):
        raise ValueError('Noon seller/offer not identified')
    seller_name=seller.locator('strong').inner_text().strip()
    buy=page.get_by_role('button',name='Add To Cart',exact=True)
    if not buy.is_visible() or not buy.is_enabled():
        raise ValueError('Noon purchase availability not confirmed')
    return {'key':f"noon:{sku}:{seller_id[1]}:{query['offer_code'][0]}",
            'store':'noon','name':title[:180],'variant':target.get('description','Exact offer'),
            'sku':sku,'price':price,'currency':'EGP','available':True,'seller':seller_name,
            'url':target['url'],'target':target}


def collect_browser(store, client):
    parser={'amazon-browser':amazon_item,'noon-browser':noon_item}[store['provider']]
    items=[]
    for target in store['targets']:
        page=client.open(target['url'])
        items.append(parser(page,target))
    return items


def confirm_browser(item, store, client):
    parser={'amazon-browser':amazon_item,'noon-browser':noon_item}[store['provider']]
    again=parser(client.open(item['url']),item['target'])
    return again['key']==item['key'] and again['price']==item['price'] and again['available']
