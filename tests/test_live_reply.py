import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from personal_search import reply,process

class LiveReplyRouting(unittest.TestCase):
    def test_product_link_routes_to_live_reader(self):
        with patch('live_reply.live_reply',return_value='fresh read') as reader:
            result=reply('https://www.amazon.eg/dp/B0C9QT2J6W/',{'items':{}},{'stores':[]},datetime.now(timezone.utc))
        self.assertEqual(result,'fresh read');reader.assert_called_once()
    def test_live_budget_preserves_queued_request(self):
        updates=[{'update_id':i,'message':{'chat':{'type':'private','id':i},'text':'https://www.amazon.eg/dp/B0C9QT2J6W/'}} for i in range(1,4)]
        cursor={};sent=[]
        with patch('live_reply.live_reply',return_value='fresh read'):
            process(updates,cursor,{'items':{}},{'stores':[]},lambda *args:sent.append(args),lambda x:None)
        self.assertEqual(len(sent),2);self.assertEqual(cursor['offset'],3)
