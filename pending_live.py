"""Check queue metadata in memory; no requests/chat IDs are persisted or logged."""
import json,os
from pathlib import Path
from personal_search import api

def main():
    cursor_path=Path('data/search-cursor.json')
    cursor=json.loads(cursor_path.read_text()) if cursor_path.exists() else {}
    updates=api('getUpdates',{'offset':cursor.get('offset',0),'limit':20,'timeout':0,'allowed_updates':['message']})
    needed=any(u.get('message',{}).get('chat',{}).get('type')=='private' and u.get('message',{}).get('text','').strip().removeprefix('/search ').startswith(('https://','http://')) for u in updates)
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as out:out.write('needed='+str(needed).lower()+'\n')
    print('Pending product-link request:',needed)

if __name__=='__main__':
    try:main()
    except Exception:
        print('Queue inspection failed without logging private data.')
        raise SystemExit(1)
