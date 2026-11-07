"""Local-only browser runner; isolated profile, no personal browser credentials."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import watcher
from robots import Robots

ROOT=Path(__file__).resolve().parent
runtime=os.environ.get('BFI_RUNTIME')
if runtime:
    sys.path.insert(0,runtime)


class BrowserClient:
    def __init__(self, host, context):
        self.host=host; self.context=context; self.page=context.new_page();self.last=0
        response=self.page.goto('https://'+host+'/robots.txt',wait_until='domcontentloaded',timeout=30000)
        if response is None or response.status not in (200,404):
            raise ValueError('Cannot verify robots access')
        text=self.page.locator('body').inner_text() if response.status==200 else ''
        if response.status==200 and 'user-agent:' not in text.lower():
            raise ValueError('Robots response is not a rules file')
        self.rules=Robots(text)
    def open(self,url):
        if urlsplit(url).scheme!='https' or urlsplit(url).hostname!=self.host:
            raise ValueError('URL outside configured store')
        if not self.rules.can_fetch(watcher.UA,url):
            raise ValueError('Access disallowed by robots.txt')
        time.sleep(max(0,3-(time.monotonic()-self.last)));self.last=time.monotonic()
        self.page.goto(url,wait_until='domcontentloaded',timeout=45000)
        if urlsplit(self.page.url).hostname!=self.host:
            raise ValueError('Unexpected store redirect')
        return self.page
    def get(self,path):
        page=self.open('https://'+self.host+path)
        page.wait_for_function("document.querySelector('script') && document.documentElement.innerHTML.includes('window.__STORE__')",timeout=25000)
        return page.content()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--notify',action='store_true')
    parser.add_argument('--config',default=str(ROOT/'local-config.json'))
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright
    folder=ROOT/'local-data';folder.mkdir(exist_ok=True)
    # Windows lock is released by the OS on crash; concurrent loops cannot send twice.
    import msvcrt
    lock=(folder/'runner.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: raise SystemExit('Local watcher is already running')
    while True:
        if args.notify:
            from local_secrets import load_secrets
            for key,value in load_secrets(ROOT/'local-secrets.bin').items():os.environ[key]=value
        config=json.loads(Path(args.config).read_text(encoding='utf-8'))
        config['execution_location']='local'
        result=1
        try:
            with sync_playwright() as p:
                # Local network returns ERR_HTTP2_PROTOCOL_ERROR for Noon; use
                # standard HTTP/1.1, without proxying or changing access controls.
                browser=p.chromium.launch(channel='chrome',headless=True,args=['--disable-http2'])
                context=browser.new_context(locale='en-GB')
                clients={}
                def factory(host):
                    if host not in clients:clients[host]=BrowserClient(host,context)
                    return clients[host]
                result=watcher.run(config,folder/'state.json',folder/'status.json',args.notify,client_factory=factory)
                (folder/'runner-error.json').unlink(missing_ok=True)
                browser.close()
        except Exception as exc:
            # Never print browser/network exception URLs or credentials.
            watcher.save(folder/'runner-error.json',{'at':watcher.stamp(watcher.utcnow()),'error':type(exc).__name__})
        if args.once:raise SystemExit(result)
        time.sleep(max(300,config.get('interval_seconds',900)))

if __name__=='__main__': main()
