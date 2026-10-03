import time

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
import uvicorn

from src.database import get_database_connection, reset_database
from src.pipeline import download_and_ingest_data
from src.search import live_graph_rag_query

# 1. Initialize the FastAPI web server environment
app = FastAPI(title="Enterprise NoSQL Graph-RAG Engine")

# 2. Establish our template route paths pointing to the folder hierarchy
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. Establish initial global database collection handles
chunks_col, edges_col = get_database_connection()

@app.get("/", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    """
    Serves the front-end D3 force-directed visual map layout to the user's web browser.
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/ingest")
async def handle_ingestion(limit: int = Query(default=150, ge=1, le=1000)):
    """
    Triggers the high-throughput batch pipeline to pull verified Wikipedia articles 
    and forge vector/graph networks completely offline.
    """
    try:
        # Clear out old collections to avoid multi-run metric pollution
        reset_database(chunks_col, edges_col)
        
        # Run the streaming batch execution engine
        count = await run_in_threadpool(download_and_ingest_data, chunks_col, edges_col, limit)
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "count": count,
            "edges": edges_col.count_documents({}),
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/query")
async def handle_graph_rag_query(
    intent: str,
    depth: int = Query(default=3, ge=1, le=5),
):
    """
    Captures text strings, runs multi-hop recursive structural lookups on MongoDB indexing,
    and returns force-directed node-edge layout maps.
    """
    if not intent:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Query string intent parameter missing."})
        
    try:
        # Pass parameters down into our custom recursive traversal layer
        graph_payload = await run_in_threadpool(
            live_graph_rag_query,
            intent,
            chunks_col,
            edges_col,
            max_depth=depth,
        )
        return JSONResponse(content=graph_payload)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/stats")
async def get_database_stats():
    """Return live collection, index, and relationship metrics from MongoDB."""
    try:
        ping_started = time.perf_counter()
        chunks_col.database.command("ping")
        ping_ms = round((time.perf_counter() - ping_started) * 1000, 1)
        relationship_breakdown = list(edges_col.aggregate([
            {"$group": {"_id": "$relationship_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]))
        top_entities = list(edges_col.aggregate([
            {"$match": {"relationship_type": {"$in": ["CONTAINS", "STRUCTURAL_INDEX"]}}},
            {"$group": {"_id": "$target", "mentions": {"$sum": 1}}},
            {"$sort": {"mentions": -1}},
            {"$limit": 6},
        ]))

        return {
            "status": "connected",
            "database": chunks_col.database.name,
            "documents": chunks_col.count_documents({}),
            "edges": edges_col.count_documents({}),
            "entity_mentions": edges_col.count_documents({
                "relationship_type": {"$in": ["CONTAINS", "STRUCTURAL_INDEX"]}
            }),
            "semantic_bridges": edges_col.count_documents({"relationship_type": "CROSS_ARTICLE_SEMANTIC_BRIDGE"}),
            "indexes": len(chunks_col.index_information()) + len(edges_col.index_information()),
            "ping_ms": ping_ms,
            "relationships": [
                {"type": item["_id"] or "Uncategorized", "count": item["count"]}
                for item in relationship_breakdown
            ],
            "top_entities": [
                {"name": item["_id"], "mentions": item["mentions"]}
                for item in top_entities
            ],
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "disconnected", "message": str(e)})

if __name__ == "__main__":
    # Boot up the server on standard network channel highway port 8000
    print("🚀 Launching local enterprise NoSQL web tier server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)