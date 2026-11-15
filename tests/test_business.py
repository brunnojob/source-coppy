import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from server import app as api

class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();api.DB_PATH=Path(self.tmp.name)/'test.sqlite3';api.initialize()
        self.clients=[]
        self.owner=self.seed('a');self.other=self.seed('b');self.cashier=self.seed('a-cash','cashier',self.owner['business_id'])
        self.client=TestClient(api.app)
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def seed(self,suffix,role='owner',business=None):
        user=api.ident();business=business or api.ident();email=suffix+'@example.test'
        with api.transaction() as db:
            db.execute('INSERT OR IGNORE INTO businesses VALUES(?,?,?,?)',(business,suffix,'BRL',api.now()))
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1,?)',(user,business,email,suffix,api.password_hash('Test-Password-123!'),role,api.now()))
            token=api.issue_session(db,user)
        return {'id':user,'business_id':business,'headers':{'Authorization':'Bearer '+token},'email':email}
    def call(self,method,path,data=None,actor=None):return self.client.request(method,path,json=data,headers=(actor or self.owner)['headers'])
    def product(self,stock=5,price=4500):
        r=self.call('POST','/products',{'sku':api.ident(),'name':'Cut','price_cents':price,'stock':stock,'track_stock':True});self.assertEqual(r.status_code,200,r.text);return r.json()['id']
    def shift(self,actor=None):
        r=self.call('POST','/shifts/open',{'opening_cents':10000},actor);self.assertEqual(r.status_code,200,r.text);return r.json()['id']
    def sale(self,product,key=None,qty=1,actor=None,**kwargs):
        return self.call('POST','/sales',dict(items=[{'product_id':product,'quantity':qty}],payment_method='cash',idempotency_key=key or api.ident(),**kwargs),actor)
    def test_login_logout_and_expiry(self):
        r=self.client.post('/auth/login',json={'email':self.owner['email'],'password':'Test-Password-123!'});self.assertEqual(r.status_code,200,r.text)
        headers={'Authorization':'Bearer '+r.json()['token']};self.assertEqual(self.client.get('/me',headers=headers).status_code,200)
        self.client.post('/auth/logout',headers=headers);self.assertEqual(self.client.get('/me',headers=headers).status_code,401)
        self.assertEqual(self.client.get('/products').status_code,401)
    def test_failed_login_rate_limit_persists(self):
        for _ in range(10):self.assertEqual(self.client.post('/auth/login',json={'email':self.owner['email'],'password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'email':self.owner['email'],'password':'wrong'}).status_code,429)
    def test_tenant_isolation_and_roles(self):
        product=self.product();self.assertEqual(self.call('GET','/products',actor=self.other).json(),[])
        self.assertEqual(self.call('POST',f'/products/{product}/stock',{'delta':1,'reason':'restock'},self.other).status_code,404)
        self.assertEqual(self.call('POST','/products',{'sku':'x','name':'Bad','price_cents':10,'stock':1},self.cashier).status_code,403)
        self.assertEqual(self.call('GET','/reports',actor=self.cashier).status_code,403)
        self.assertEqual(self.call('GET','/tasks',actor=self.cashier).status_code,403)
    def test_sale_atomic_stock_and_idempotency(self):
        product=self.product();self.shift();key=api.ident();first=self.sale(product,key,qty=2);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['total_cents'],9000);self.assertEqual(self.sale(product,key,qty=2).json()['id'],first.json()['id'])
        self.assertEqual(self.call('GET','/products').json()[0]['stock'],3)
        self.assertEqual(self.sale(product,key,qty=1).status_code,409)
        self.assertEqual(self.sale(product,qty=4).status_code,409)
        self.assertEqual(self.call('GET','/products').json()[0]['stock'],3)
    def test_concurrent_sales_cannot_oversell(self):
        product=self.product(stock=1);self.shift()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda _:self.sale(product).status_code,range(2)))
        self.assertEqual(sorted(statuses),[200,409]);self.assertEqual(self.call('GET','/products').json()[0]['stock'],0)
    def test_refund_once_and_cash_reconciliation(self):
        product=self.product();shift=self.shift();sale=self.sale(product).json()
        for _ in range(2):self.assertEqual(self.call('POST',f"/sales/{sale['id']}/refund",{'reason':'Customer returned'}).status_code,200)
        self.assertEqual(self.call('GET','/products').json()[0]['stock'],5)
        self.assertEqual(self.call('GET','/reports').json()['net_cents'],0)
        close=self.call('POST',f'/shifts/{shift}/close',{'declared_cents':10000});self.assertEqual(close.json()['difference_cents'],0)
        self.assertEqual(self.sale(product).status_code,409)
    def test_cross_shift_refund_is_counted_in_refund_shift(self):
        product=self.product();first=self.shift();sale=self.sale(product).json()
        self.call('POST',f'/shifts/{first}/close',{'declared_cents':14500})
        second=self.shift();self.call('POST',f"/sales/{sale['id']}/refund",{'reason':'Next day return'})
        r=self.call('POST',f'/shifts/{second}/close',{'declared_cents':5500});self.assertEqual(r.json()['expected_cents'],5500)
    def test_prices_and_invalid_inputs_are_server_controlled(self):
        product=self.product();self.shift(self.cashier)
        self.assertEqual(self.sale(product,actor=self.cashier,discount_cents=1).status_code,403)
        self.assertEqual(self.sale(product,qty=0).status_code,422)
        self.assertEqual(self.sale(product,qty=True).status_code,422)
        payload={'items':[{'product_id':product,'quantity':1,'price_cents':1}],'payment_method':'cash','idempotency_key':api.ident()}
        self.assertEqual(self.call('POST','/sales',payload).status_code,422)
    def test_invites_one_use_and_session_revocation(self):
        invite=self.call('POST','/team/invites',{'email':'new@example.test','name':'New','role':'cashier'}).json()
        payload={'token':invite['token'],'password':'Another-Password-123!'}
        self.assertEqual(self.client.post('/auth/accept-invite',json=payload).status_code,200)
        self.assertEqual(self.client.post('/auth/accept-invite',json=payload).status_code,400)
        r=self.client.post('/auth/login',json={'email':'new@example.test','password':'Another-Password-123!'}).json()
        self.call('PATCH',f"/team/{r['user']['id']}",{'role':'cashier','active':False})
        self.assertEqual(self.client.get('/me',headers={'Authorization':'Bearer '+r['token']}).status_code,401)
    def test_optimistic_versions_and_assignee_scope(self):
        product=self.product();row=self.call('GET','/products').json()[0]
        data={'name':'New name','price_cents':4500,'version':row['version']};self.assertEqual(self.call('PATCH',f'/products/{product}',data).status_code,200)
        self.assertEqual(self.call('PATCH',f'/products/{product}',data).status_code,409)
        self.assertEqual(self.call('POST','/tasks',{'title':'Test','assignee_id':self.other['id']}).status_code,404)
    def test_project_sync_is_private_and_versioned(self):
        project=api.ident();payload={'name':'Site','document':{'version':2,'pages':[{'name':'Home'}]},'version':0}
        self.assertEqual(self.call('POST',f'/projects/{project}',payload).json()['version'],1)
        self.assertEqual(self.call('POST',f'/projects/{project}',payload).status_code,409)
        self.assertEqual(self.call('GET',f'/projects/{project}',actor=self.other).status_code,404)
        self.assertEqual(self.call('GET','/projects',actor=self.other).json(),[])
    def test_password_change_revokes_sessions(self):
        r=self.call('POST','/auth/password',{'old_password':'Test-Password-123!','new_password':'New-Password-456!'})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.call('GET','/me').status_code,401)
    def test_backup_can_restore_data(self):
        self.product();backup=Path(self.tmp.name)/'backup.sqlite3'
        import sqlite3
        with api.connect() as source,sqlite3.connect(backup) as dest:source.backup(dest)
        with sqlite3.connect(backup) as db:self.assertEqual(db.execute('select count(*) from products').fetchone()[0],1)
    def test_streamed_body_limit_rejects_oversized_requests(self):
        chunks=(b'x'*1_000_000 for _ in range(26))
        r=self.client.post('/auth/login',content=chunks,headers={'Content-Type':'application/json'})
        self.assertEqual(r.status_code,413,r.text)
    def test_operator_bootstrap_and_recovery_commands(self):
        from unittest.mock import patch
        from server import manage
        with patch('sys.argv',['manage','bootstrap','--business','New business','--email','bootstrap@example.test','--name','Owner']), patch('getpass.getpass',return_value='Bootstrap-Password-123!'):
            manage.main()
        result=self.client.post('/auth/login',json={'email':'bootstrap@example.test','password':'Bootstrap-Password-123!'})
        self.assertEqual(result.status_code,200,result.text)
        token=result.json()['token']
        with patch('sys.argv',['manage','reset-password','--email','bootstrap@example.test']), patch('getpass.getpass',return_value='Recovered-Password-123!'):
            manage.main()
        self.assertEqual(self.client.get('/me',headers={'Authorization':'Bearer '+token}).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'email':'bootstrap@example.test','password':'Recovered-Password-123!'}).status_code,200)
    def test_cors_rejects_unlisted_origins(self):
        r=self.client.options('/products',headers={'Origin':'https://attacker.invalid','Access-Control-Request-Method':'POST'})
        self.assertEqual(r.status_code,400);self.assertNotIn('access-control-allow-origin',r.headers)
if __name__=='__main__':unittest.main()
