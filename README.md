# MCP Review Intelligence

A working, local-first review evidence product with CSV/JSON import, SQLite storage, deduplication, deterministic sentiment, traceable aspect themes, product/period comparisons, MCP tools and a browser workspace.

## Run the product

Python 3.11+; no third-party packages, model API keys or scraper subscription required.

```bash
python server.py --web --demo
```

Open **http://127.0.0.1:8766**. Import reviews, choose a product and sample window, inspect sentiment and exact source excerpts, compare products or nonoverlapping time periods, then download the report. Demo records in `examples/reviews.json` are explicitly synthetic.

For MCP stdio:

```bash
python server.py --db data/reviews.sqlite
```

Supports MCP **2025-11-25** initialization, ping, tools/list and tools/call over newline-delimited stdin/stdout JSON-RPC. The browser API is a separate localhost companion, not an advertised MCP HTTP transport.

## MCP client configuration

```json
{
  "mcpServers": {
    "review-intelligence": {
      "command": "python",
      "args": ["/absolute/path/mcp-review-intelligence/server.py", "--db", "/absolute/path/mcp-review-intelligence/data/reviews.sqlite"]
    }
  }
}
```

Use real absolute paths and your Python 3.11+ executable.

| Tool | Behavior |
|---|---|
| `import_reviews` | Atomic CSV/JSON import with schema validation and stable-ID/content deduplication |
| `list_products` | Product inventory with review and source counts |
| `list_reviews` | Paginated, date/source/language-filtered evidence |
| `summarize_sentiment` | Defined-sample sentiment distribution, separate source ratings, aspect themes and supporting excerpts |
| `compare_products` | Side-by-side evidence and coverage disclosures; no arbitrary winner |
| `compare_periods` | Descriptive negative-share change across nonoverlapping windows with source evidence |

## Import contract

```json
{
  "reviews": [{
    "id": "review-123",
    "product": "Headphones A",
    "source": "permitted-export",
    "url": "https://example.com/reviews/123",
    "published_at": "2026-01-01",
    "text": "Great sound, but difficult setup.",
    "rating": 4,
    "language": "en"
  }]
}
```

Required: id, product, source, url, published_at, text. Optional: captured_at (defaults to import time), rating (1–5), language (en/other, defaults to en). CSV uses the same headers and standard quoted fields; supply it as `{ "csv": "..." }`. Supply either CSV or reviews, not both. Imports are limited to 1,000 rows and transport messages to 1 MB. Use successive imports for larger datasets.

Dates accept YYYY-MM-DD or timezone-qualified ISO datetimes. A date-only `to` filter includes the complete day. Publication after capture and future timestamps are rejected. Repeated stable IDs and identical normalized text within one product/source are deduplicated. Conflicting text for an existing ID rejects the entire import rather than silently overwriting evidence. Distinct sources retain their provenance.

## Analysis and limits

- English positive/negative lexicons with local negation handling; mixed reviews remain mixed.
- Explicit unscored label for unsupported languages.
- Six aspect dictionaries: reliability, performance, usability, value, support and quality.
- Exact excerpts, IDs, source URLs and publication timestamps behind every theme.
- Empty/sparse-sample indicators and source/language/date coverage.
- Theme evidence capped at 20 excerpts per aspect; retrieve complete records through paginated `list_reviews`.
- Source ratings are separate from text sentiment. No invented quotes, causality claims or inferred personal traits.

The lexical baseline does not reliably detect sarcasm, contextual meaning, or aspect-specific polarity. Sentiment from reviewers is a selected sample, not a population estimate. Period comparisons are descriptive, not significance tests. There is no automatic external scraping; import permitted exports with their original source links.

## Verification

```bash
python -m unittest discover -s tests -v
```

Tests exercise mixed/negated/unsupported-language sentiment, exact evidence, rating separation, CSV quoting and malformed rows, deduplication, atomic conflict rollback, date filters, pagination, sparse/empty samples, comparisons, persistence and a subprocess MCP client. Web integration tests check the browser and API, size limits and host/origin rejection.

`engine.py` owns schema and analysis. `core.py` owns protocol/localhost transport. `web/` provides the browser workflow without remote scripts or analytics. SQLite data stays local; the server binds to 127.0.0.1 and rejects foreign Host/Origin headers. This is a local product, not a public multi-tenant service. Integration tests use the included protocol client; universal host certification is not claimed.

Protocol reference: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

MIT licensed. Example reviews are synthetic, not copied from customers.
