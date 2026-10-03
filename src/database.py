import os

from pymongo import MongoClient, ASCENDING

def get_database_connection():
    client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
    db = client[os.getenv("MONGODB_DATABASE", "nosql_enterprise_graph_rag")]
    
    chunks_collection = db["knowledge_chunks"]
    edges_collection = db["graph_edges"]
    
    # Build fast relational search trees
    chunks_collection.create_index([("chunk_id", 1)], unique=True)
    edges_collection.create_index([("source", ASCENDING), ("target", ASCENDING)])
    edges_collection.create_index([("target", ASCENDING)])
    
    return chunks_collection, edges_collection



def build_production_indices(chunks_col, edges_col):
    """
    Compiles optimized background layout structures.
    Without this, recursive graph traversals will bottleneck your CPU.
    """
    print("🏗️ Compiling multi-key high-speed compound indexes...")
    
    # 1. Index document IDs for instant atomic fetches
    chunks_col.create_index([("chunk_id", 1)], unique=True)
    
    # 2. Index the graph network adjacency fields
    # Forward trace mapping: matching from the parent context chunk
    edges_col.create_index([("source", ASCENDING), ("target", ASCENDING)])
    
    # Reverse trace mapping: matching where specific entities are referenced
    edges_col.create_index([("target", ASCENDING)])
    
    print("🚀 Database indices successfully compiled.")

def reset_database(chunks_col, edges_col):
    chunks_col.drop()
    edges_col.drop()
    build_production_indices(chunks_col, edges_col)

