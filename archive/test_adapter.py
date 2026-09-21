import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import bench

class Response:
    status_code=200
    def __init__(self, value): self.content=json.dumps(value).encode()

class AdapterTest(unittest.TestCase):
    def test_same_semantics_and_short_llm(self):
        q=dict(state={'held':False},stage='intent',questions={'intent':dict(type='choice',instructions='Choose',criteria={'a':'one','b':'two'})})
        responses=[{'answers':{'intent':{'choice':'a','probabilities':{'a':.9,'b':.1}}}},
                   {'choices':[{'finish_reason':'stop','message':{'content':'{"intent":"a"}'}}]}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(bench,'HERE',Path(tmp)), patch.object(bench,'credential',return_value='local-test-credential'):
            saved=[]
            for p,body in zip(('jev','deepseek'),responses):
                c=bench.Client(p)
                with patch.object(c.session,'post',return_value=Response(body)) as post:
                    r=c.call(q,p); saved.append(post.call_args.kwargs['json'])
                    self.assertEqual(r['value'],{'intent':'a'})
                    self.assertEqual(len(c.records),1)
            self.assertEqual(json.loads(saved[1]['messages'][1]['content']),{k:saved[0][k] for k in ('state','questions')})
            self.assertEqual(saved[1]['thinking'],{'type':'disabled'})

    def test_failed_request_is_counted_and_globally_stops(self):
        q=dict(state={},stage='intent',questions={'i':{'criteria':{'a':'one'}}})
        with tempfile.TemporaryDirectory() as tmp, patch.object(bench,'HERE',Path(tmp)), patch.object(bench,'credential',return_value='local-test-credential'):
            c=bench.Client('deepseek')
            with patch.object(c.session,'post',return_value=Response({'choices':[]})):
                with self.assertRaises(RuntimeError): c.call(q,'bad')
            self.assertEqual(c.count,1); self.assertEqual(c.records[0]['tag'],'bad')
            self.assertGreater(c.records[0]['seconds'],0)
            self.assertIn('body_seconds',c.records[0])
            with self.assertRaises(RuntimeError): bench.Client('jev').call(q,'later')
            self.assertFalse((Path(tmp)/'jev_attempts.jsonl').exists())

if __name__=='__main__': unittest.main()
