"""Egypt price watcher. Python standard library only; no credentials in state/logs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

UA = 'BlackFridayIntelligence/1.0'


def utcnow():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.isoformat(timespec='seconds')


def money(value, cents=False):
    try:
        number = Decimal(str(value)) / (100 if cents else 1)
        if not number.is_finite() or number <= 0 or number > 10_000_000:
            raise ValueError('Invalid price')
        return str(number.quantize(Decimal('0.01')))
    except InvalidOperation:
        raise ValueError('Invalid price') from None


class Client:
    def __init__(self, host, delay=2):
        if not re.fullmatch(r'[a-z0-9.-]+', host) or '.' not in host:
            raise ValueError('Invalid store hostname')
        self.host, self.delay, self.last = host, delay, 0
        self.robots = RobotFileParser()
        self.robots.parse(self.get('/robots.txt', check=False).splitlines())

    def get(self, path, check=True):
        url = 'https://' + self.host + path
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Invalid store path')
        if check and not self.robots.can_fetch(UA, url):
            raise ValueError('Access disallowed by robots.txt')
        for attempt in range(3):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                with urlopen(Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'}), timeout=20) as response:
                    if urlsplit(response.url).hostname != self.host:
                        raise ValueError('Store redirected to another host')
                    data = response.read(8_000_001)
                    if len(data) > 8_000_000:
                        raise ValueError('Response too large')
                    return data.decode('utf-8')
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ValueError(f'HTTP {exc.code} at {path}') from None
                time.sleep(min(30, max(10 * (attempt + 1), int(exc.headers.get('Retry-After', '0')) if exc.headers.get('Retry-After', '').isdigit() else 0)))
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise ValueError('Store connection failed') from None
                time.sleep(2 ** attempt)

    def json(self, path):
        return json.loads(self.get(path))


def variants(store, product, cents=False):
    """Each size/color is a separate price series; never take a product's lowest price."""
    handle = product['handle']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', handle):
        raise ValueError('Invalid product handle')
    result = []
    for v in product['variants']:
        variant_id = str(v['id'])
        if not variant_id.isdigit():
            raise ValueError('Invalid variant ID')
        result.append({
            'key': f"{store['id']}:{product['id']}:{variant_id}",
            'store': store['id'], 'name': str(product['title'])[:180],
            'variant': str(v['title'])[:100], 'variant_id': variant_id,
            'sku': str(v.get('sku') or ''), 'handle': handle,
            'price': money(v['price'], cents), 'available': v.get('available') is True,
            'currency': 'EGP',
            'url': f"https://{store['host']}/products/{handle}?variant={variant_id}",
        })
    return result


def collect(store, client):
    # Currency is verified per run, not inferred from an Egyptian-looking hostname.
    currencies = re.findall(r'Shopify\.currency\s*=\s*(\{[^}]+\})', client.get('/'))
    # Ignore escaped copies inside serialized HTML; use actual JS assignments.
    currencies = [json.loads(c) for c in currencies if c.startswith('{"')]
    if not currencies or any(c.get('active') != 'EGP' for c in currencies):
        raise ValueError('Store currency is not EGP')
    result = {}
    for page in range(1, store.get('pages', 2) + 1):
        products = client.json(f'/products.json?limit=50&page={page}')['products']
        for product in products:
            for item in variants(store, product):
                result[item['key']] = item
        if len(products) < 50:
            break
    # Explicit product handles stay monitored even if they leave the discovery window.
    for handle in store.get('pinned_handles', []):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', handle):
            raise ValueError('Invalid pinned handle')
        for item in variants(store, client.json(f'/products/{handle}.js'), cents=True):
            result[item['key']] = item
    if not result:
        raise ValueError('No variants returned; provider may have changed')
    return list(result.values())


def confirm(item, store, client):
    # A fresh product endpoint must agree with the feed on exact variant and price.
    product = client.json(f"/products/{item['handle']}.js")
    return any(v['key'] == item['key'] and v['price'] == item['price']
               and v['available'] for v in variants(store, product, cents=True))


def event_id(item):
    return hashlib.sha256(f"{item['key']}:{item['price']}".encode()).hexdigest()


def observe(state, item, now, drop_percent=15):
    records = state['items']
    entry = records.setdefault(item['key'], {'history': []})
    cutoff = now - timedelta(days=30)
    history = [h for h in entry['history'] if datetime.fromisoformat(h['at']) >= cutoff]
    # Compare with the lowest *observed in-stock* price before this run, not compare_at_price.
    past = [Decimal(h['price']) for h in history
            if h['available'] and datetime.fromisoformat(h['at']) <= now - timedelta(minutes=10)]
    pending = entry.get('pending')
    if pending and (now - datetime.fromisoformat(pending['at']) > timedelta(hours=6)
                    or not item['available'] or Decimal(item['price']) > Decimal(pending['price'])):
        pending = None
    if item['available'] and past:
        baseline = min(past)
        price = Decimal(item['price'])
        if price <= baseline * (1 - Decimal(str(drop_percent)) / 100):
            pending = {'at': stamp(now), 'price': item['price'], 'baseline': str(baseline)}
    sent = state['sent']
    if pending and event_id(item) in sent:
        pending = None
    entry['pending'] = pending
    sample = {'at': stamp(now), 'price': item['price'], 'available': item['available']}
    # Retain changes and daily checkpoints, with rolling 30-day retention.
    if not history or any(history[-1][k] != sample[k] for k in ('price', 'available')) or history[-1]['at'][:10] != sample['at'][:10]:
        history.append(sample)
    entry.update({'history': history, 'last_seen': stamp(now), 'item': item})
    return pending


def message(item, pending):
    old, new = Decimal(pending['baseline']), Decimal(item['price'])
    percent = (old - new) * 100 / old
    return (f"انخفاض سعر مرصود — {item['store']}\n{item['name']}\n"
            f"المقاس/اللون: {item['variant']} | SKU: {item['sku']}\n"
            f"{new} جنيه، مقابل أقل سعر سابق رصدناه خلال 30 يومًا: {old} جنيه ({percent:.1f}%)\n"
            "تأكد السعر والتوفر بقراءة ثانية لنفس الاختيار. السجل يبدأ من أول تشغيل؛ ليس ضمانًا لأقل سعر بالسوق.\n"
            "راجع الشحن والكوبونات والمقاس عند الدفع؛ عروض التطبيق/السلة قد تختلف.\n"
            f"{item['url']}")


def send_telegram(text):
    token, chat = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return False
    body = json.dumps({'chat_id': chat, 'text': text, 'link_preview_options': {'is_disabled': True}}).encode()
    try:
        request = Request(f'https://api.telegram.org/bot{token}/sendMessage', data=body,
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=20) as response:
            if json.load(response).get('ok') is not True:
                raise ValueError('Telegram rejected notification')
    except Exception:
        # Never print exception URLs: the Telegram URL contains the token.
        raise ValueError('Telegram send failed; check secrets and bot permissions') from None
    return True


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def load_state(path):
    if not Path(path).exists():
        return {'version': 1, 'items': {}, 'sent': {}}
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    if state.get('version') != 1 or not isinstance(state.get('items'), dict) or not isinstance(state.get('sent'), dict):
        raise ValueError('Invalid state; refusing to discard historical prices')
    return state


def run(config, state_path, report_path, notify=False):
    now = utcnow()
    state = load_state(state_path)
    state['sent'] = {k: v for k, v in state['sent'].items() if datetime.fromisoformat(v) > now - timedelta(days=90)}
    report = {'at': stamp(now), 'mode': 'notify' if notify else 'collect-only',
              'telegram_configured': bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')),
              'providers': [], 'notifications_sent': 0, 'candidates': 0, 'errors': []}
    budget = config.get('max_alerts_per_run', 5)
    for store in sorted(config['stores'], key=lambda s: s.get('priority', 99)):
        if not store.get('enabled', False):
            continue
        try:
            client = Client(store['host'])
            items = collect(store, client)
            status = {'store': store['id'], 'variants': len(items),
                      'in_stock': sum(i['available'] for i in items), 'status': 'ok'}
            for item in items:
                pending = observe(state, item, now, config.get('drop_percent', 15))
                if not pending:
                    continue
                report['candidates'] += 1
                if notify and report['telegram_configured'] and report['notifications_sent'] < budget:
                    try:
                        if confirm(item, store, client) and send_telegram(message(item, pending)):
                            state['sent'][event_id(item)] = stamp(now)
                            state['items'][item['key']]['pending'] = None
                            report['notifications_sent'] += 1
                            # Durable on runner immediately; workflow persists remotely even on failure.
                            save(state_path, state)
                    except Exception as exc:
                        report['errors'].append(f"{store['id']}: {type(exc).__name__} during verification/notification")
            report['providers'].append(status)
        except Exception as exc:
            report['providers'].append({'store': store['id'], 'status': 'error', 'error': str(exc)[:160]})
    # Missing/failed products are not treated as a zero price or out of stock.
    state['items'] = {k: v for k, v in state['items'].items()
                      if datetime.fromisoformat(v['last_seen']) > now - timedelta(days=35)}
    if not report['providers']:
        report['errors'].append('No enabled providers')
    save(state_path, state)
    save(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report['errors']) or any(p['status'] == 'error' for p in report['providers']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--state', default='data/state.json')
    parser.add_argument('--report', default='data/status.json')
    parser.add_argument('--notify', action='store_true')
    parser.add_argument('--test-telegram', action='store_true')
    args = parser.parse_args()
    if args.test_telegram:
        if not send_telegram('اختبار اتصال Black Friday Intelligence Egypt — ليست رسالة عرض.'):
            raise SystemExit('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Secrets first')
        print('Telegram test delivered')
        return
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    if not 0 < config.get('drop_percent', 15) < 100:
        raise ValueError('drop_percent must be between 0 and 100')
    raise SystemExit(run(config, args.state, args.report, args.notify))


if __name__ == '__main__':
    main()
