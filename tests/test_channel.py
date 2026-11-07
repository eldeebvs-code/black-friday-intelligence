import json
import os
import unittest
from unittest.mock import patch, MagicMock
import watcher

class ChannelRouting(unittest.TestCase):
    def test_offers_channel_does_not_replace_private_destination(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"ok":true}'
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'test','TELEGRAM_CHAT_ID':'private-test'}), patch('watcher.urlopen',return_value=response) as call:
            watcher.send_telegram('offer',chat_id='@NOV_OFFERS')
            self.assertEqual(json.loads(call.call_args.args[0].data)['chat_id'],'@NOV_OFFERS')
            watcher.send_telegram('health')
            self.assertEqual(json.loads(call.call_args.args[0].data)['chat_id'],'private-test')

