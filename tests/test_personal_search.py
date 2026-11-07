import unittest
from datetime import datetime,timezone,timedelta
from personal_search import search,reply,process,APIError

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.config={'stores':[{'id':'shop','enabled':True}]}
        self.entry={'last_seen':self.now.isoformat(),'item':{'store':'shop','name':'Samsung charger 45W','variant':'White','sku':'EP-4511','price':'500.00','available':True,'url':'https://shop.example/p/1'}}
        self.state={'items':{'one':self.entry}}
    def test_arabic_alias_and_watts(self):
        self.assertEqual(len(search('سامسونج ٤٥ وات',self.state,self.config,self.now)),1)
        self.assertEqual(search('samsung 25w',self.state,self.config,self.now),[])
    def test_stale_and_disabled_and_stock(self):
        self.entry['last_seen']=(self.now-timedelta(days=2)).isoformat()
        self.assertEqual(search('samsung',self.state,self.config,self.now),[])
        self.entry['last_seen']=self.now.isoformat()
        self.config['stores'][0]['enabled']=False
        self.assertEqual(search('samsung',self.state,self.config,self.now),[])
        self.config['stores'][0]['enabled']=True;self.entry['item']['available']=False
        self.assertEqual(search('samsung',self.state,self.config,self.now),[])
    def test_url_is_lookup_only(self):
        self.assertEqual(search('http://127.0.0.1/secret',self.state,self.config,self.now),[])
        self.assertEqual(len(search('https://shop.example/p/1?tracking=x',self.state,self.config,self.now)),1)
    def test_reply_is_explicitly_observed(self):
        answer=reply('/search samsung',self.state,self.config,self.now)
        self.assertIn('آخر رصد',answer);self.assertIn('500.00',answer)
    def test_private_only_offset_no_personal_storage(self):
        updates=[{'update_id':1,'message':{'chat':{'type':'group','id':1},'text':'samsung'}},{'update_id':2,'message':{'chat':{'type':'private','id':123},'text':'samsung'}}]
        sent=[];cursor={};saved=[]
        process(updates,cursor,self.state,self.config,lambda *x:sent.append(x),lambda x:saved.append(dict(x)))
        self.assertEqual(len(sent),1);self.assertEqual(cursor,{'offset':3})
        process(updates,cursor,self.state,self.config,lambda *x:sent.append(x),lambda x:None)
        self.assertEqual(len(sent),1)
    def test_failed_send_not_acknowledged(self):
        cursor={}
        def fail(*x):raise APIError(429)
        with self.assertRaises(APIError):process([{'update_id':4,'message':{'chat':{'type':'private','id':123},'text':'samsung'}}],cursor,self.state,self.config,fail,lambda x:None)
        self.assertEqual(cursor,{})
