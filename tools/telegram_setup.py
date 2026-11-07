"""Reply privately to /myid. Never publish Telegram updates or identifiers."""
import json
import os
import time
from urllib.request import Request, urlopen


def api(token, method, payload):
    try:
        req = Request(f'https://api.telegram.org/bot{token}/{method}',
                      data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise ValueError()
        return result['result']
    except Exception:
        # Exception URLs can contain the bot token. Do not print Telegram bodies.
        raise ValueError('Telegram request failed. Check the saved token and bot configuration.') from None


def select_request(updates, now):
    matches = {}
    for update in updates:
        msg = update.get('message', {})
        chat = msg.get('chat', {})
        sender = msg.get('from', {})
        if (msg.get('text', '').strip() == '/myid'
                and chat.get('type') == 'private'
                and isinstance(chat.get('id'), int)
                and chat['id'] == sender.get('id')
                and sender.get('is_bot') is False
                and 0 <= now - msg.get('date', 0) <= 3600):
            matches[chat['id']] = msg
    if len(matches) > 1:
        raise ValueError('More than one private setup requester; refusing to choose a recipient.')
    return next(iter(matches.values()), None)


def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise ValueError('Save TELEGRAM_BOT_TOKEN in repository Actions secrets first.')
    if api(token, 'getWebhookInfo', {}).get('url'):
        raise ValueError('This bot uses a webhook. No webhook settings were changed.')
    request = select_request(api(token, 'getUpdates', {'limit': 100, 'timeout': 0}), time.time())
    if not request:
        raise ValueError('No recent private /myid request. Send /myid to your own bot and run setup again.')
    chat_id = request['chat']['id']
    api(token, 'sendMessage', {
        'chat_id': chat_id,
        'text': 'رقم محادثتك هو:\n' + str(chat_id)
                + '\n\nاحفظ الرقم فقط في GitHub Actions Secret باسم TELEGRAM_CHAT_ID. '
                  'هذه رسالة إعداد، وليست تنبيه عرض. لا تشارك توكن البوت.',
        'reply_parameters': {'message_id': request['message_id']},
    })
    print('Setup reply delivered privately in Telegram. No identifiers were written to GitHub.')


if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None