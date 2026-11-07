"""Bounded private Telegram search. Never persist user messages or chat IDs."""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit
from watcher import save

HELP = ('أرسل اسم المنتج والموديل، مثل: سامسونج 45W، أو رابط المنتج.\n'
        'الاسم يبحث في سجل آخر 24 ساعة. رابط المنتج المباشر يُفحص الآن بالمتصفح؛ المصادر التي ترفض الاتصال تظهر كفشل، وليس سعرًا قديمًا.\n'
        'الرد في دورة التشغيل التالية (حوالي 15 دقيقة وقد يتأخر).\n'
        '/sources المصادر\n/privacy الخصوصية\nلا توجد متابعة شخصية تلقائية بعد البحث حاليًا.')
ALIASES={'سامسونج':'samsung','شاحن':'charger','شواحن':'charger','راس':'charger','يوجرين':'ugreen','راڤ':'rav','وات':'w'}

def words(text):
    text=text.lower().translate(str.maketrans('أإآى٠١٢٣٤٥٦٧٨٩','اااي0123456789'))
    text=re.sub(r'[\u064b-\u065f\u0640]','',text)
    text=re.sub(r'(\d+)\s*(?:وات|watt|w)\b',r'\1w',text)
    return [ALIASES.get(w,w) for w in re.findall(r'[a-z0-9\u0621-\u064a]+',text)]

def search(query,state,config,now):
    active={s['id'] for s in config['stores'] if s.get('enabled')}
    tokens=words(query)
    link=urlsplit(query) if query.startswith(('https://','http://')) else None
    found=[]
    for entry in state.get('items',{}).values():
        item=entry['item']
        if item['store'] not in active or not item.get('available'):continue
        seen=datetime.fromisoformat(entry['last_seen'])
        if not now-timedelta(hours=24)<=seen<=now:continue
        if link:
            target=urlsplit(item['url'])
            match=(target.hostname,target.path.rstrip('/'))==(link.hostname,link.path.rstrip('/'))
        else:
            hay=set(words(' '.join(str(item.get(k,'')) for k in ['name','variant','sku','store'])))
            match=bool(tokens) and all(t in hay for t in tokens)
        if match:found.append((item,entry['last_seen']))
    return sorted(found,key=lambda pair:Decimal(pair[0]['price']))[:5]

def reply(text,state,config,now):
    text=text.strip()
    command=text.split(' ',1)[0].split('@')[0].lower()
    if command in ('/start','/help','/search') and (command!='/search' or ' ' not in text):return HELP
    if command=='/privacy':return 'نعالج الرسالة ومعرف المحادثة في الذاكرة للرد فقط؛ لا نحفظهما في GitHub أو السجلات. تليجرام يحتفظ بالمحادثة وفق سياسته. لا ترسل بيانات شخصية أو توكنات.'
    if command=='/sources':return 'المصادر المفعلة في هذا البحث:\n'+'\n'.join(s['id']+': '+s.get('scope','نطاق محدد') for s in config['stores'] if s.get('enabled'))+'\nأمازون المحلي غير مشمول في البحث السحابي.'
    if command=='/search':text=text.split(' ',1)[1].strip()
    elif text.startswith('/'):return HELP
    if not 2<=len(text)<=180:return 'اكتب اسم المنتج والموديل أو رابطًا مباشرًا، بحد أقصى 180 حرفًا.'
    if text.startswith(('https://','http://')):
        from live_reply import live_reply
        return live_reply(text)
    rows=search(text,state,config,now)
    if not rows:return 'لم أجد مطابقة متوفرة وحديثة في المصادر التي نراقبها. هذا لا يعني أن المنتج غير موجود بالسوق. جرّب الموديل بالإنجليزية أو /sources لمعرفة التغطية.'
    lines=['نتائج مرصودة مرتبة بالسعر؛ قد تختلف المواصفات والبائع. ليست ضمانًا لأفضل سعر بالسوق أو أصالة المنتج.']
    for item,seen in rows:
        lines.append(f"{item['name'][:140]}\n{item.get('variant','')[:100]}\n{item['price']} جنيه | {item['store']} | البائع: {item.get('seller','المتجر')}\nآخر رصد UTC: {seen}\n{item['url']}")
    return '\n\n'.join(lines)+'\n\nتحقق من السعر والتوفر والشحن والضمان في الرابط قبل الشراء.'

class APIError(Exception):
    def __init__(self,code=0):self.code=code

def api(method,body):
    token=os.environ['TELEGRAM_BOT_TOKEN']
    try:
        req=Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=20) as r:data=json.load(r)
        if not data.get('ok'):raise APIError(data.get('error_code',0))
        return data['result']
    except HTTPError as exc:raise APIError(exc.code) from None
    except APIError:raise
    except Exception:raise APIError() from None

def process(updates,cursor,state,config,send,persist):
    counts={};total=0;live_count=0
    for update in updates:
        uid=update['update_id']
        if uid<cursor.get('offset',0):continue
        msg=update.get('message',{});chat=msg.get('chat',{})
        if chat.get('type')=='private' and not msg.get('from',{}).get('is_bot'):
            cid=chat['id'];counts[cid]=counts.get(cid,0)+1
            if counts[cid]<=3:
                text=msg.get('text','')
                is_live=text.strip().removeprefix('/search ').startswith(('https://','http://'))
                if is_live and os.getenv('LIVE_BROWSER_READY')=='false':
                    break  # A new link arrived after queue inspection; defer safely.
                if is_live and live_count>=2:
                    break  # Leave this and subsequent updates queued, not discarded.
                live_count+=int(is_live)
                answer=reply(text,state,config,datetime.now(timezone.utc))
                try:send(cid,answer)
                except APIError as e:
                    if e.code!=403:raise
                total+=1
        cursor['offset']=uid+1
        persist(cursor)
    return total

def main():
    config=json.loads(Path('config.json').read_text(encoding='utf-8'))
    state=json.loads(Path('data/state.json').read_text(encoding='utf-8'))
    path=Path('data/search-cursor.json')
    cursor=json.loads(path.read_text()) if path.exists() else {}
    if api('getWebhookInfo',{}).get('url'):raise APIError(409)
    me=api('getMe',{})
    if not cursor.get('announced'):
        api('setMyCommands',{'commands':[{'command':'start','description':'ابدأ البحث'},{'command':'search','description':'ابحث باسم المنتج والموديل'},{'command':'sources','description':'المصادر المتاحة'},{'command':'help','description':'المساعدة'},{'command':'privacy','description':'الخصوصية'}]})
        api('sendMessage',{'chat_id':config['offers_channel'],'text':'البحث الشخصي التجريبي متاح الآن 🔎\nابحث داخل الأسعار المرصودة للمصادر المدعومة. الرد في دورة التشغيل التالية، حوالي 15 دقيقة وقد يتأخر. ليست تغطية لكل السوق.','reply_markup':{'inline_keyboard':[[{'text':'ابحث عن منتج','url':'https://t.me/'+me['username']+'?start=search'}]]}})
        cursor['announced']=True;cursor['bot_username']=me['username'];save(path,cursor)
    updates=api('getUpdates',{'offset':cursor.get('offset',0),'limit':20,'timeout':0,'allowed_updates':['message']})
    def send(cid,answer):
        api('sendMessage',{'chat_id':cid,'text':answer[:4000],'link_preview_options':{'is_disabled':True}})
        time.sleep(1.1)
    total=process(updates,cursor,state,config,send,lambda value:save(path,value))
    save(Path('data/search-status.json'),{'at':datetime.now(timezone.utc).isoformat(),'status':'ok','replies':total,'bot_username':me['username']})
    print('Search receiver completed; replies:',total)

if __name__=='__main__':
    try:main()
    except Exception:
        print('Search receiver failed; check token, webhook, permissions or connectivity. No user data logged.')
        raise SystemExit(1)

