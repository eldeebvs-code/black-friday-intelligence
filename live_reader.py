"""Read exact public product pages in an isolated browser. No checkout/login."""
import re
from urllib.parse import urlsplit
from watcher import money,UA
from robots import Robots
from browser_sources import amazon_item,noon_item,cash
from jumia import product_items
from catalogue import parse_variants

HOSTS={'www.amazon.eg':'amazon','www.noon.com':'noon','www.jumia.com.eg':'jumia','eshop.vodafone.com.eg':'vodafone','eshop.orange.eg':'orange'}

def validate_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443):raise ValueError('Unsupported public store URL')
    store=HOSTS[u.hostname]
    patterns={'amazon':r'/dp/[A-Z0-9]{10}(?:/|$)','noon':r'/egypt-en/.+/(?:N|Z)[A-Z0-9]+/p/','jumia':r'^/[a-zA-Z0-9.-]+\.html$','vodafone':r'^/en/prod/[a-z0-9-]+$','orange':r'^/en/[a-z0-9-]+/p/[a-z0-9-]+$'}
    if not re.search(patterns[store],u.path):raise ValueError('An exact product URL is required')
    return store,u

def orange_item(page,url):
    summary=page.locator('[aria-label="Purchase summary"]')
    summary.wait_for(timeout=30000)
    title=summary.locator('h1').inner_text().replace('Out of Stock','').strip()
    price=money(summary.locator('[itemprop="price"]').inner_text().replace(',','').strip())
    currency=summary.locator('[itemprop="priceCurrency"]').get_attribute('content')
    if currency!='EGP':raise ValueError('Orange currency unverified')
    stocks={node.get_attribute('content') for node in summary.locator('[itemprop="availability"]').all()}
    if len(stocks)!=1:raise ValueError('Conflicting Orange stock declarations')
    stock=stocks.pop()
    if stock not in ('https://schema.org/InStock','https://schema.org/OutOfStock'):raise ValueError('Orange availability unverified')
    variants=page.locator('[aria-label="Variant selection"]')
    text=variants.inner_text()
    storage=re.search(r'Selected Storage:\s*([^\n]+)',text)
    color=re.search(r'Selected Color:\s*([^\n]+)',text)
    if not storage or not color:raise ValueError('Orange exact selected variant missing')
    variant=storage[1].strip()+' / '+color[1].strip()
    return {'key':'orange:'+urlsplit(url).path+':'+variant,'store':'orange','sku':urlsplit(url).path.rsplit('/',1)[1],'name':title[:180],'variant':variant,'price':price,'currency':'EGP','available':stock.endswith('/InStock'),'seller':'Orange Egypt E-Shop','url':url,'warranty':'راجع تفاصيل الضمان في صفحة أورانج؛ لا نفترضه من اسم المنتج'}

def read_product(browser,url):
    store,u=validate_url(url)
    context=browser.new_context(locale='en-GB')
    page=context.new_page()
    def guard(route):
        if route.request.is_navigation_request() and route.request.frame==page.main_frame:
            destination=urlsplit(route.request.url)
            if destination.scheme!='https' or destination.hostname!=u.hostname:
                route.abort();return
        route.continue_()
    page.route('**/*',guard)
    try:
        response=page.goto('https://'+u.hostname+'/robots.txt',wait_until='domcontentloaded',timeout=25000)
        if response is None or response.status not in (200,404):raise ValueError('Cannot verify robots access')
        rules=page.locator('body').inner_text() if response.status==200 else ''
        if response.status==200 and 'user-agent:' not in rules.lower():raise ValueError('Invalid robots rules response')
        if not Robots(rules).can_fetch(UA,url):raise ValueError('Product path disallowed by robots')
        response=page.goto(url,wait_until='domcontentloaded',timeout=35000)
        if response is None or response.status>=400:raise ValueError('Product page unavailable')
        if urlsplit(page.url).hostname!=u.hostname:raise ValueError('Unexpected redirect')
        if store=='amazon':
            asin=re.search(r'/dp/([A-Z0-9]{10})',u.path)[1]
            items=[amazon_item(page,{'asin':asin,'url':url,'description':'الاختيار الحالي في رابط المنتج'})]
        elif store=='noon':
            sku=re.search(r'/((?:N|Z)[A-Z0-9]+)/p/',u.path)[1]
            items=[noon_item(page,{'sku':sku,'url':url,'description':'العرض والبائع الحاليان؛ راجع الأصالة والضمان'})]
        elif store=='jumia':
            page.locator('h1').wait_for(timeout=25000)
            items=product_items(page.content(),{'id':store,'host':u.hostname},u.path,money)
        elif store=='vodafone':
            page.locator('h1').first.wait_for(timeout=25000)
            items=parse_variants(page.content(),{'id':store,'host':u.hostname},u.path,money)
        else:items=[orange_item(page,url)]
        return items
    finally:context.close()
