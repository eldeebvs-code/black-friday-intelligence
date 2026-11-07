"""One smoke run sends the exact user-facing live response to the bot owner."""
import os
from live_reply import live_reply
from personal_search import api
url='https://www.amazon.eg/-/en/Samsung-Type-C-Charge-Adapter-EP-T2510NBEGWW/dp/B0C9QT2J6W/'
answer=live_reply(url)
api('sendMessage',{'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':'اختبار القراءة الحية للبوت\n\n'+answer,'link_preview_options':{'is_disabled':True}})
if not answer.startswith('فحص مباشر الآن'):raise SystemExit(1)
print('Live read response accepted by Telegram for configured owner. No private data logged.')
