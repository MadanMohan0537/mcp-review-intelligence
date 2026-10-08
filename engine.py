import csv
import hashlib
import io
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from core import tool

S = {"type":"string","minLength":1,"maxLength":2000}
FILTERS = {"product":S,"from":S,"to":S,"source":S,"language":S}
POSITIVE = {"great","good","excellent","love","fast","easy","reliable","helpful","smooth","affordable","comfortable","perfect"}
NEGATIVE = {"bad","poor","broken","slow","hate","terrible","crash","crashes","expensive","unreliable","difficult","refund","disappointed","fails"}
ASPECTS = {"reliability":{"broken","crash","crashes","fails","reliable","unreliable","bug","bugs"},
           "performance":{"fast","slow","speed","latency","loading"},
           "usability":{"easy","difficult","interface","setup","navigation","confusing"},
           "value":{"price","expensive","affordable","cost","refund","value"},
           "support":{"support","service","helpful","response","agent"},
           "quality":{"quality","comfortable","durable","material","perfect"}}


def date(value):
    if not isinstance(value,str) or len(value)>40: raise ValueError("Invalid ISO date")
    try: parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: raise ValueError("Invalid ISO date") from None
    if parsed.tzinfo is None:
        if len(value)!=10: raise ValueError("Datetime must include a timezone")
        parsed=parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def sentiment(text, language="en"):
    if language != "en": return {"label":"unscored","score":None,"method":"English lexicon baseline; unsupported language"}
    tokens=re.findall(r"[a-z']+",text.lower()); positive=negative=0
    for i,token in enumerate(tokens):
        sign=1 if token in POSITIVE else -1 if token in NEGATIVE else 0
        context=tokens[max(0,i-3):i]
        # Negation stops at common clause boundaries; mixed clauses remain visible.
        if "but" in context: context=context[context.index("but")+1:]
        if any(t in {"not","never","no","isn't","wasn't","don't","doesn't","can't"} for t in context): sign=-sign
        positive+=sign>0; negative+=sign<0
    label="mixed" if positive and negative else "positive" if positive else "negative" if negative else "neutral"
    return {"label":label,"score":(positive-negative)/(positive+negative) if positive+negative else 0,
            "positive_terms":positive,"negative_terms":negative,"method":"negation-aware English lexicon v1; sarcasm is not inferred"}


def themes(text):
    words=set(re.findall(r"[a-z']+",text.lower()))
    return [name for name,terms in ASPECTS.items() if words & terms]


class ReviewIntelligence:
    name="mcp-review-intelligence"
    def __init__(self,path):
        if path!=":memory:": Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path);self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
         CREATE TABLE IF NOT EXISTS reviews(product TEXT,id TEXT,source TEXT,url TEXT,published_at TEXT,captured_at TEXT,text TEXT,rating REAL,language TEXT,content_hash TEXT,PRIMARY KEY(product,source,id));
         CREATE INDEX IF NOT EXISTS review_window ON reviews(product,published_at);
        ''')
        record={"type":"object","properties":{"id":S,"product":S,"source":S,"url":S,"published_at":S,"captured_at":S,"text":{"type":"string","minLength":1,"maxLength":10000},"rating":{"type":"number","minimum":1,"maximum":5},"language":{"type":"string","enum":["en","other"]}},"required":["id","product","source","url","published_at","text"],"additionalProperties":False}
        self.tools=[
          tool("import_reviews","Atomically import provenance-preserving review records or a quoted CSV with the same column names. Stable IDs and duplicate text are deduplicated per product/source.",{"reviews":{"type":"array","items":record,"maxItems":1000},"csv":{"type":"string","maxLength":800000}},write=True),
          tool("list_products","List imported products and source coverage.",{}),
          tool("list_reviews","Filter a defined sample; return source-linked evidence with pagination.",{**FILTERS,"offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":100}},["product"]),
          tool("summarize_sentiment","Observed sentiment distribution, ratings and traceable aspect themes. Ratings and inferred text sentiment are separate.",FILTERS,["product"]),
          tool("compare_products","Compare review samples with source/language/date coverage caveats.",{"products":{"type":"array","items":S,"maxItems":10},"from":S,"to":S,"source":S,"language":S},["products"]),
          tool("compare_periods","Compare two nonoverlapping, inclusive time windows for one product; disclose coverage differences.",{"product":S,"before_from":S,"before_to":S,"after_from":S,"after_to":S,"source":S,"language":S},["product","before_from","before_to","after_from","after_to"]),
        ]
    def normalize(self,row):
        from core import validate
        schema=self.tools[0]["inputSchema"]["properties"]["reviews"]["items"]
        validate(row,schema,"review")
        parsed=urlparse(row["url"])
        if parsed.scheme not in ("https","http") or not parsed.hostname or parsed.username or parsed.password: raise ValueError("Review URL must be a source URL without credentials")
        text=row["text"].strip()
        if not text: raise ValueError("Review text is empty")
        published=date(row["published_at"]);captured=date(row.get("captured_at",datetime.now(timezone.utc).isoformat()))
        now=datetime.now(timezone.utc).isoformat()
        if published>now or captured>now or published>captured: raise ValueError("Review publication/capture dates are inconsistent or in the future")
        content_hash=hashlib.sha256(re.sub(r"\s+"," ",text.lower()).encode()).hexdigest()
        return (row["product"],row["id"],row["source"],row["url"],published,captured,text,row.get("rating"),row.get("language","en"),content_hash)
    def select(self,a):
        query="SELECT * FROM reviews WHERE product=?";params=[a["product"]]
        for name,op in [("from",">="),("to","<=")]:
            if name in a:query+=f" AND published_at{op}?";params.append(date(a[name])+"" if name=="from" or len(a[name])!=10 else date(a[name]).replace("T00:00:00", "T23:59:59.999999"))
        if "from" in a and "to" in a and date(a["from"])>date(a["to"]):raise ValueError("from must precede to")
        for name in ("source","language"):
            if name in a:query+=f" AND {name}=?";params.append(a[name])
        return [dict(r) for r in self.db.execute(query+" ORDER BY published_at,id",params)]
    def summarize(self,a):
        rows=self.select(a);distribution=Counter();aspects={};ratings=[]
        for row in rows:
            analysis=sentiment(row["text"],row["language"]);distribution[analysis["label"]]+=1
            if row["rating"] is not None:ratings.append(row["rating"])
            if row["language"]=="en":
                for aspect in themes(row["text"]):
                    aspects.setdefault(aspect,[]).append({"id":row["id"],"source":row["source"],"url":row["url"],"published_at":row["published_at"],"excerpt":row["text"][:300],"sentiment":analysis["label"]})
        return {"product":a["product"],"sample_size":len(rows),"status":"empty_sample" if not rows else "sparse_sample" if len(rows)<5 else "observed_sample",
                "filters":a,"coverage":{"sources":dict(Counter(r["source"] for r in rows)),"languages":dict(Counter(r["language"] for r in rows)),"first_date":rows[0]["published_at"] if rows else None,"last_date":rows[-1]["published_at"] if rows else None},
                "sentiment_distribution":dict(distribution),"rated_sample_size":len(ratings),"average_source_rating":sum(ratings)/len(ratings) if ratings else None,
                "themes":[{"aspect":aspect,"review_count":len(evidence),"evidence":evidence[:20]} for aspect,evidence in sorted(aspects.items(),key=lambda x:(-len(x[1]),x[0]))],
                "limitations":["Selected review sample, not population sentiment or proof of causality.","Deterministic English lexical baseline; sarcasm, context and aspect-level polarity require human review.","Theme evidence is capped at 20 excerpts; use list_reviews for the complete filtered sample."]}
    def call(self,name,a):
        if name=="import_reviews":
            if ("reviews" in a)==("csv" in a):raise ValueError("Supply reviews or csv, exactly one")
            rows=a.get("reviews")
            if "csv" in a:
                reader=csv.DictReader(io.StringIO(a["csv"]));rows=[]
                if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError("CSV requires unique named columns")
                for row in reader:
                    if None in row or any(v is None for v in row.values()):raise ValueError("Malformed CSV row")
                    row={k:v for k,v in row.items() if v!=""}
                    if "rating" in row:
                        try:row["rating"]=float(row["rating"])
                        except ValueError:raise ValueError("Invalid source rating") from None
                    rows.append(row)
            if not rows or len(rows)>1000:raise ValueError("Import between 1 and 1000 reviews")
            normalized=[self.normalize(r) for r in rows];inserted=duplicates=0
            with self.db:
                for row in normalized:
                    existing=self.db.execute("SELECT content_hash FROM reviews WHERE product=? AND source=? AND id=?",(row[0],row[2],row[1])).fetchone()
                    if existing and existing[0]!=row[-1]:raise ValueError("Conflicting text for an existing source review ID; no changes committed")
                    same=self.db.execute("SELECT 1 FROM reviews WHERE product=? AND source=? AND content_hash=?",(row[0],row[2],row[-1])).fetchone()
                    if existing or same:duplicates+=1;continue
                    self.db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?,?)",row);inserted+=1
            return {"inserted":inserted,"duplicates":duplicates,"received":len(rows)}
        if name=="list_products":
            return {"products":[dict(r) for r in self.db.execute("SELECT product,COUNT(*) review_count,COUNT(DISTINCT source) source_count FROM reviews GROUP BY product ORDER BY product")]}
        if name=="list_reviews":
            rows=self.select(a);start=a.get("offset",0);limit=a.get("limit",100)
            return {"total":len(rows),"reviews":rows[start:start+limit],"next_offset":start+limit if start+limit<len(rows) else None}
        if name=="summarize_sentiment":return self.summarize(a)
        if name=="compare_products":
            if len(set(a["products"]))<2:raise ValueError("Choose at least two different products")
            filters={k:v for k,v in a.items() if k!="products"}
            samples=[self.summarize({**filters,"product":p}) for p in dict.fromkeys(a["products"])]
            return {"samples":samples,"coverage_comparable":len({json.dumps(s["coverage"]["sources"],sort_keys=True) for s in samples})==1,"caveat":"Source counts, date ranges and languages may differ; no overall winner is inferred."}
        if name=="compare_periods":
            if date(a["before_from"])>date(a["before_to"]) or date(a["after_from"])>date(a["after_to"]) or date(a["before_to"])>=date(a["after_from"]):raise ValueError("Choose ordered nonoverlapping windows")
            common={k:a[k] for k in ("product","source","language") if k in a}
            before=self.summarize({**common,"from":a["before_from"],"to":a["before_to"]});after=self.summarize({**common,"from":a["after_from"],"to":a["after_to"]})
            def share(s):return s["sentiment_distribution"].get("negative",0)/s["sample_size"] if s["sample_size"] else None
            b,c=share(before),share(after)
            return {"before":before,"after":after,"negative_share_change_pp":(c-b)*100 if b is not None and c is not None else None,"caveat":"Descriptive change in selected samples; mixed reviews are reported separately. Not a causal or statistically validated product effect."}
        raise ValueError("Unknown tool")
    def demo(self):
        self.call("import_reviews",{"reviews":json.loads((Path(__file__).parent/"examples"/"reviews.json").read_text())})
    def collect(self):raise ValueError("Review collection is explicit CSV/JSON import; no unattended external scraping")
