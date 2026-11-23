import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import server

class ModelApiTests(unittest.TestCase):
    def test_catalog_validation_and_busy(self):
        app=ThreadingHTTPServer(('127.0.0.1',0),server.ChatHandler)
        threading.Thread(target=app.serve_forever,daemon=True).start()
        self.addCleanup(app.server_close)
        self.addCleanup(app.shutdown)
        def request(path, data=None):
            c=HTTPConnection(*app.server_address,timeout=5)
            c.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),{'Host':'127.0.0.1:3000','Content-Type':'application/json'})
            r=c.getresponse(); result=r.status,json.loads(r.read()); c.close(); return result
        code, data=request('/api/models')
        self.assertEqual(code,200)
        self.assertEqual(len(data['models']),4)
        self.assertEqual({model['id']: model['context'] for model in data['models']}, {
            'qwen9b': 16384, 'qwen4b': 65536, 'wizard7b': 2048, 'qwen30b': 4096,
        })
        self.assertEqual(request('/api/models/load',{'model':'../bad'})[0],400)
        with server.RUNTIME.lock:
            self.assertEqual(request('/api/models/load',{'model':'qwen9b'})[0],409)
            self.assertEqual(request('/api/chat',{'messages':[{'role':'user','content':'Hi'}]})[0],409)
        with patch.object(server.RUNTIME,'load') as load, patch.object(server.RUNTIME,'model','test-model'), patch('server.MODEL'):
            self.assertEqual(request('/api/models/load',{'model':'qwen9b'})[1]['model'],'test-model')
            load.assert_called_once_with('qwen9b')

if __name__=='__main__': unittest.main()
