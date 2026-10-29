import time

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
MIN_COSINE_SIMILARITY = 0.30

def live_graph_rag_query(search_intent, chunks_col, edges_col, max_depth=2):
    started_at = time.perf_counter()
    query_vector = embedding_model.encode(search_intent).tolist()
    
    all_chunks = list(chunks_col.find(
        {},
        {"chunk_id": 1, "title": 1, "text_content": 1, "vector_embedding": 1},
    ))
    if not all_chunks:
        return {"status": "error", "message": "No documents are indexed yet. Stream a dataset first."}

    vectors = np.asarray([chunk["vector_embedding"] for chunk in all_chunks], dtype=np.float32)
    scores = cosine_similarity([query_vector], vectors)[0]
    anchor_index = int(np.argmax(scores))
    anchor_chunk = all_chunks[anchor_index]
    top_score = float(scores[anchor_index])
            
    if not anchor_chunk or top_score < MIN_COSINE_SIMILARITY:
        return {
            "status": "error",
            "message": "No relevant data found. Try a search that better matches the indexed passages.",
        }
        
    # 3. USE PYMONGO NATIVE GRAPH LOOKUP PIPELINE
    # This runs directly inside the database, completely preventing freezes!
    pipeline = [
        {"$match": {"source": anchor_chunk["chunk_id"]}},
        {
            "$graphLookup": {
                "from": "graph_edges",
                "startWith": "$target",
                "connectFromField": "target",
                "connectToField": "source",
                "as": "network_chain",
                "maxDepth": max_depth
            }
        }
    ]
    
    graph_results = list(edges_col.aggregate(pipeline))
    
    node_ids = {anchor_chunk["chunk_id"]}
    output_links = []
    seen_links = set()

    for item in graph_results:
        for edge in [item, *item.get("network_chain", [])]:
            source = edge["source"]
            target = edge["target"]
            relationship = edge.get("relationship_type", "LINK")
            node_ids.update((source, target))
            signature = (source, target, relationship)
            if signature not in seen_links:
                seen_links.add(signature)
                output_links.append({"source": source, "target": target, "label": relationship})

    document_ids = [node_id for node_id in node_ids if node_id.startswith("wiki_node_")]
    titles = {
        chunk["chunk_id"]: chunk.get("title", chunk["chunk_id"])
        for chunk in chunks_col.find(
            {"chunk_id": {"$in": document_ids}},
            {"chunk_id": 1, "title": 1},
        )
    } if document_ids else {}
    output_nodes = []
    for node_id in sorted(node_ids):
        is_document = node_id.startswith("wiki_node_")
        output_nodes.append({
            "id": node_id,
            "label": titles.get(node_id, node_id) if is_document else node_id,
            "type": "document" if is_document else "entity",
            "val": 25 if node_id == anchor_chunk["chunk_id"] else (17 if is_document else 12),
        })

    return {
        "status": "success",
        "anchor_title": anchor_chunk["title"],
        "anchor_excerpt": anchor_chunk["text_content"],
        "nodes": output_nodes,
        "links": output_links,
        "anchor_score": top_score,
        "depth": max_depth,
        "query_time_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }


def recursive_hop_traversal(current_node, current_depth, max_depth, edges_col, chunks_col, graph_data, visited, added_edges):
    """
    Core Relational Logic: Recursively jumps down graph network paths
    by looking up out-of-core indices inside the NoSQL adjacency collection.
    """
    if current_depth >= max_depth:
        return
        
    # Query the background binary index for all relationships stemming from the current node
    links = list(edges_col.find({"source": current_node}))
    
    for link in links:
        target_node = link["target"]
        rel_type = link.get("relationship_type", "LINKED_TO")
        
        # Step A: Register the discovered Node into UI properties array if unseen
        if target_node not in visited:
            visited.add(target_node)
            
            # Determine if target is another wiki document node or an NLP structural entity
            is_doc = target_node.startswith("wiki_node_")
            node_label = target_node
            
            if is_doc:
                doc_meta = chunks_col.find_one({"chunk_id": target_node}, {"title": 1})
                if doc_meta:
                    node_label = doc_meta.get("title", target_node)
                    
            graph_data["nodes"].append({
                "id": target_node,
                "label": node_label,
                "type": "document" if is_doc else "entity",
                "val": 18 if is_doc else 12  # Visual scaling parameters
            })
            
        # Step B: Log the structural Edge data connection vector
        edge_signature = f"{current_node}->{target_node}"
        if edge_signature not in added_edges:
            added_edges.add(edge_signature)
            graph_data["edges"].append({
                "source": current_node,
                "target": target_node,
                "label": rel_type
            })
            
        # Step C: Recursively descend deeper down the multi-hop path chain
        recursive_hop_traversal(
            current_node=target_node,
            current_depth=current_depth + 1,
            max_depth=max_depth,
            edges_col=edges_col,
            chunks_col=chunks_col,
            graph_data=graph_data,
            visited=visited,
            added_edges=added_edges
        )
