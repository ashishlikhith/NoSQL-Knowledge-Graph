# Fieldnotes Graph Lab

A local knowledge-graph explorer built with FastAPI, PyMongo, Sentence Transformers, spaCy, and Cytoscape.js. It streams a bounded sample of WikiText-103, stores document vectors and graph edges in MongoDB, finds the closest document to a search, and asks MongoDB to traverse its graph neighborhood with `$graphLookup`.

## Features

- Semantic anchor search using the local `all-MiniLM-L6-v2` embedding model.
- Interactive force-directed graph with document and entity nodes. Select a node to search around it.
- Adjustable MongoDB graph traversal depth (1-5 hops).
- Live MongoDB document, edge, entity-mention, index-count, and ping metrics.
- MongoDB aggregation charts for relationship types and most-mentioned entities.
- Configurable streaming limit (150, 500, or 1,000 documents) and batched semantic-edge writes.
- Query response timing and anchor similarity score.

## Requirements

- Python 3.10 or newer.
- MongoDB running locally, or a MongoDB connection URI.
- Internet access for the initial WikiText/model downloads and the dashboard's CDN-hosted Cytoscape.js and Chart.js assets.
- The spaCy `en_core_web_sm` model.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
python app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first run downloads the embedding model and dataset as needed. Start MongoDB before launching the app.

To use a non-default MongoDB server or database, set these optional environment variables before starting Python:

```powershell
$env:MONGODB_URI = "mongodb://localhost:27017/"
$env:MONGODB_DATABASE = "nosql_enterprise_graph_rag"
python app.py
```

## MongoDB data model

Database: `nosql_enterprise_graph_rag` by default.

### `knowledge_chunks` - document tier

| Field | Stored value |
| --- | --- |
| `chunk_id` | Unique identifier such as `wiki_node_1`; uniquely indexed. |
| `title` | First line of the accepted WikiText record, shortened to 50 characters. |
| `text_content` | Source text excerpt, truncated to 800 characters. |
| `vector_embedding` | 384-dimensional float vector from `all-MiniLM-L6-v2`. |
| `extracted_entities` | Deduplicated spaCy PERSON, ORG, and GPE mentions. |

### `graph_edges` - adjacency-list tier

| Field | Stored value |
| --- | --- |
| `source` | Starting node ID, generally a document ID. |
| `target` | Entity name or another document ID. |
| `relationship_type` | `CONTAINS` for extracted entities or `CROSS_ARTICLE_SEMANTIC_BRIDGE` for vector-similar documents. |
| `weight` | Cosine similarity for semantic-bridge edges. |

The edge collection has a compound `(source, target)` index and a `target` index. Re-ingestion clears both collections and recreates their indexes before writing new records.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Dashboard. |
| `GET` | `/api/stats` | Live MongoDB health, collection counts, index count, relationship aggregation, and top entities. |
| `POST` | `/api/ingest?limit=150` | Reset and ingest up to 1,000 valid records. `limit` is constrained to 1-1,000. |
| `GET` | `/api/query?intent=history&depth=3` | Find a semantic anchor and return its graph neighborhood; `depth` is constrained to 1-5. |

FastAPI's interactive API docs are at `/docs` while the server is running.

## Ingestion and search flow

1. The pipeline streams WikiText-103 and filters short records and markup headings.
2. Sentence Transformers embeds each 800-character excerpt; spaCy extracts people, organizations, and locations.
3. PyMongo writes documents and `CONTAINS` edges in batches. A vectorized cosine-similarity matrix adds cross-document edges above the configured threshold.
4. Search embeds the query, compares it against stored vectors, and selects the closest document as its anchor.
5. MongoDB's native `$graphLookup` traverses outgoing edges. The API returns graph nodes, links, source excerpt, similarity, and elapsed query time.

## Notes and limitations

- WikiText-103 is a language-model dataset derived from Wikipedia articles; records are text segments, not guaranteed complete or clean article pages.
- The similarity matrix uses $O(n^2)$ compute and memory. The UI caps selectable ingestion at 1,000 records to keep this local demo bounded; increase limits only after profiling and batching for your hardware.
- The local embedding and spaCy models are loaded by the Python modules at startup. First startup may take a while.
- Cytoscape.js and Chart.js are loaded from a CDN, so the dashboard needs internet access for those visualizations.
- This is a local demonstration, not a hardened multi-user deployment. Ingestion resets the active collections and should not be run against shared production data.
