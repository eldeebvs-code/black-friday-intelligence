"""Run locally only. Token entry is hidden and is never written to disk."""
import getpass
import json
from urllib.request import Request, urlopen


def main():
    token = getpass.getpass('Bot token (hidden): ').strip()
    try:
        request = Request('https://api.telegram.org/bot' + token + '/getUpdates',
                          data=b'{"limit":20}', headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise ValueError()
        chats = {}
        for update in result.get('result', []):
            msg = update.get('message') or update.get('channel_post') or {}
            chat = msg.get('chat', {})
            if 'id' in chat:
                chats[chat['id']] = chat.get('type', '')
        if not chats:
            print('No recent messages. Open your bot, press Start, send a message and retry.')
        for chat_id, kind in chats.items():
            print(f'Chat ID: {chat_id} ({kind})')
    except Exception:
        print('Unable to read updates. Check the token/network and whether a webhook is configured.')


if __name__ == '__main__':
    main()
