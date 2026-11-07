import json
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
from live_reader import read_product

URLS={
'amazon':'https://www.amazon.eg/-/en/Samsung-Type-C-Charge-Adapter-EP-T2510NBEGWW/dp/B0C9QT2J6W/',
'noon':'https://www.noon.com/egypt-en/super-fast-charging-45w-pd-charger-black/N70095444V/p/?o=ba76f2e0d46f829e',
'jumia':'https://www.jumia.com.eg/samsung-super-fast-charger-head-45w-with-type-c-port-compatible-with-phones-black-135314517.html',
'vodafone':'https://eshop.vodafone.com.eg/en/prod/ugreen-gan-fast-charger-45w-usb-c-eu',
'orange':'https://eshop.orange.eg/en/smart-phones/p/honor-x9e-pro'}

def main():
    result={'at':datetime.now(timezone.utc).isoformat(),'purpose':'Live transport/extraction test, NOT equivalent-product comparison or recommendations','stores':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for store,url in URLS.items():
            try:
                items=read_product(browser,url)
                result['stores'].append({'store':store,'status':'ok','items':items})
            except Exception as exc:
                result['stores'].append({'store':store,'status':'error','error_type':type(exc).__name__,'error':str(exc).splitlines()[0][:180]})
        browser.close()
    result['completed_at']=datetime.now(timezone.utc).isoformat()
    Path('data').mkdir(exist_ok=True)
    Path('data/live-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return int(any(s['status']!='ok' for s in result['stores']))

if __name__=='__main__':raise SystemExit(main())
