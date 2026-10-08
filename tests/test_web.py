import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

class WebIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        cls.proc=subprocess.Popen([sys.executable,'server.py','--db',':memory:','--web','--port',str(cls.port)],cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        for _ in range(40):
            try:
                connection=http.client.HTTPConnection('127.0.0.1',cls.port,timeout=.2);connection.request('GET','/');response=connection.getresponse();response.read();connection.close();return
            except OSError:time.sleep(.05)
        cls.proc.terminate();raise RuntimeError('Browser companion did not start')
    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate();cls.proc.wait(timeout=5);cls.proc.stdout.close();cls.proc.stderr.close()
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        connection.request(method,path,body=body,headers=headers or {});response=connection.getresponse();status=response.status;data=response.read();connection.close();return status,data
    def test_browser_assets(self):
        for path in ['/','/app.js','/style.css']:
            status,data=self.request('GET',path);self.assertEqual(status,200);self.assertGreater(len(data),100)
        self.assertEqual(self.request('GET','/no-such-page')[0],404)
    def test_foreign_origin_and_host(self):
        self.assertEqual(self.request('GET','/',headers={'Host':'evil.example'})[0],403)
        body=json.dumps({'name':'list_products','arguments':{}})
        self.assertEqual(self.request('POST','/api/call',body,{'Origin':'https://evil.example','Content-Type':'application/json'})[0],403)
    def test_real_api(self):
        status,body=self.request('POST','/api/call',json.dumps({'name':'list_products','arguments':{}}),{'Content-Type':'application/json'})
        self.assertEqual(status,200);self.assertIn('products',json.loads(body))
    def test_write_and_inventory(self):
        price_product=Path(__file__).resolve().parents[1].name=='mcp-price-tracker'
        args={'url':'https://example.com/web-product','title':'Browser test item','observation':{'price':'19.99','currency':'USD','availability':'InStock'}} if price_product else {'reviews':[{'id':'web-1','product':'Browser test item','source':'test','url':'https://example.com/web-review','published_at':'2026-01-01','text':'Great easy setup'}]}
        status,data=self.request('POST','/api/call',json.dumps({'name':'record_product' if price_product else 'import_reviews','arguments':args}))
        self.assertEqual(status,200)
        status,data=self.request('POST','/api/call',json.dumps({'name':'list_products','arguments':{}}))
        self.assertEqual(status,200);self.assertEqual(len(json.loads(data)['products']),1)
    def test_invalid_call(self):
        self.assertEqual(self.request('POST','/api/call',json.dumps({'name':'does_not_exist','arguments':{}}))[0],400)
        self.assertEqual(self.request('POST','/api/call','broken-json')[0],400)
        self.assertEqual(self.request('POST','/api/call','')[0],400)
        self.assertEqual(self.request('POST','/api/call','x',{'Content-Length':'1000001'})[0],400)

if __name__=='__main__':unittest.main()
