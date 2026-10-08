import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import ReviewIntelligence,sentiment
from core import invoke

class ReviewTests(unittest.TestCase):
    def setUp(self):self.app=ReviewIntelligence(":memory:")
    def review(self,**kw):return {"id":"a","product":"A","source":"fixture","url":"https://example.com/review/a","published_at":"2026-01-01","text":"Great reliable quality",**kw}
    def add(self,rows):return invoke(self.app,"import_reviews",{"reviews":rows})
    def test_sentiment(self):
        for text,label in [("Excellent easy setup","positive"),("Terrible slow performance","negative"),("Great quality but expensive","mixed"),("not good","negative"),("not bad","positive"),("Arrived on Tuesday","neutral")]:
            self.assertEqual(sentiment(text)["label"],label)
    def test_unsupported_language(self):self.assertEqual(sentiment("great","other")["label"],"unscored")
    def test_evidence_and_rating(self):
        self.add([self.review(rating=2)])
        r=self.app.call("summarize_sentiment",{"product":"A"})
        self.assertEqual(r["sentiment_distribution"],{"positive":1});self.assertEqual(r["average_source_rating"],2)
        self.assertEqual(r["themes"][0]["evidence"][0]["url"],"https://example.com/review/a")
        self.assertEqual(r["themes"][0]["evidence"][0]["excerpt"],"Great reliable quality")
    def test_deduplication(self):
        self.add([self.review()]);r=self.add([self.review(),self.review(id="b")])
        self.assertEqual(r["duplicates"],2);self.assertEqual(r["inserted"],0)
    def test_conflicting_id_atomic(self):
        self.add([self.review()])
        with self.assertRaises(ValueError):self.add([self.review(id="new",text="new text"),self.review(text="changed")])
        self.assertEqual(self.app.call("list_reviews",{"product":"A"})["total"],1)
    def test_invalid_batch_atomic(self):
        with self.assertRaises(ValueError):self.add([self.review(),self.review(id="b",rating=6)])
        self.assertEqual(self.app.call("list_products",{})["products"],[])
    def test_quoted_csv(self):
        csv='id,product,source,url,published_at,text,rating\na,A,fixture,https://example.com/a,2026-01-01,"Great sound, easy setup",4\n'
        r=invoke(self.app,"import_reviews",{"csv":csv});self.assertEqual(r["inserted"],1)
        self.assertEqual(self.app.call("list_reviews",{"product":"A"})["reviews"][0]["text"],"Great sound, easy setup")
    def test_csv_shape(self):
        with self.assertRaises(ValueError):invoke(self.app,"import_reviews",{"csv":"id,id\na,b"})
        with self.assertRaises(ValueError):invoke(self.app,"import_reviews",{"csv":"id,product\na"})
    def test_filters_and_pagination(self):
        self.add([self.review(),self.review(id="b",text="Slow support",published_at="2026-01-02T16:00:00Z")])
        r=self.app.call("list_reviews",{"product":"A","limit":1})
        self.assertEqual(r["next_offset"],1)
        self.assertEqual(self.app.call("list_reviews",{"product":"A","from":"2026-01-02","to":"2026-01-02"})["total"],1)
    def test_empty_sparse(self):
        self.assertEqual(self.app.call("summarize_sentiment",{"product":"A"})["status"],"empty_sample")
        self.add([self.review()]);self.assertEqual(self.app.call("summarize_sentiment",{"product":"A"})["status"],"sparse_sample")
    def test_periods(self):
        self.add([self.review(text="bad slow"),self.review(id="b",text="great fast",published_at="2026-02-01")])
        args={"product":"A","before_from":"2026-01-01","before_to":"2026-01-31","after_from":"2026-02-01","after_to":"2026-02-28"}
        self.assertEqual(self.app.call("compare_periods",args)["negative_share_change_pp"],-100)
        with self.assertRaises(ValueError):self.app.call("compare_periods",{**args,"after_from":"2026-01-31"})
    def test_products_disclose_samples(self):
        self.add([self.review(),self.review(product="B",id="b",text="bad",source="other")])
        r=self.app.call("compare_products",{"products":["A","B"]})
        self.assertFalse(r["coverage_comparable"]);self.assertEqual(len(r["samples"]),2)
    def test_validation_dates_urls(self):
        for row in [self.review(published_at="2099-01-01"),self.review(url="javascript:alert(1)"),self.review(text="  "),self.review(rating=True)]:
            with self.assertRaises(ValueError):self.add([row])
    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/"reviews.db");app=ReviewIntelligence(path);app.call("import_reviews",{"reviews":[self.review()]});app.db.close()
            self.assertEqual(ReviewIntelligence(path).call("list_reviews",{"product":"A"})["total"],1)
    def test_protocol_client(self):
        requests=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"integration-client","version":"1"}}},
                  {"jsonrpc":"2.0","method":"notifications/initialized"},
                  {"jsonrpc":"2.0","id":2,"method":"tools/list"},
                  {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"import_reviews","arguments":{"reviews":[self.review()]}}},
                  {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"summarize_sentiment","arguments":{"product":"A"}}}]
        result=subprocess.run([sys.executable,"server.py","--db",":memory:"],cwd=Path(__file__).resolve().parents[1],input="\n".join(json.dumps(r) for r in requests)+"\n",capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);r=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(r),4);self.assertEqual(len(r[1]["result"]["tools"]),6)
        self.assertEqual(r[3]["result"]["structuredContent"]["sample_size"],1)

if __name__=="__main__":unittest.main()
