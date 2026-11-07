"""One smoke run sends the exact user-facing live response to the bot owner."""
import os,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from live_reply import format_live
from personal_search import api
path=Path('data/live-smoke.json')
report=json.loads(path.read_text(encoding='utf-8'))
if datetime.now(timezone.utc)-datetime.fromisoformat(report['completed_at'])>timedelta(minutes=5):raise SystemExit('Live evidence too old')
amazon=next(x for x in report['stores'] if x['store']=='amazon')
if amazon['status']!='ok':raise SystemExit('Amazon live check did not pass')
answer=format_live(amazon['items'],report['completed_at'])
api('sendMessage',{'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':'اختبار القراءة الحية للبوت\n\n'+answer,'link_preview_options':{'is_disabled':True}})
report['private_test_delivery']='accepted_by_telegram'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Live read response accepted by Telegram for configured owner. No private data logged.')
