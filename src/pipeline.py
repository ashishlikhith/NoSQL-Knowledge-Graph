import spacy
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from datasets import load_dataset

print("⏳ Initializing production AI models (Sentence-Transformers & spaCy)...")
# Load model onto local CPU memory matrix
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')


nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "tagger", "attribute_ruler"])
    

def download_and_ingest_data(chunks_col, edges_col, max_articles=150):
    """
    Streams verified Wikipedia Featured Articles over the network and
    flushes data arrays in optimized database bulk-operation blocks.
    """
    print("🌐 Activating live streaming connection to Wikitext-103 repository...")
    
    # Stream the dataset row-by-row to maintain zero local disk consumption overhead
    dataset = load_dataset("wikitext", "wikitext-103-v1", split="train", streaming=True)
    
    print("🚀 Pipeline Engine Active: Compiling matrix blocks...")
    
    chunk_buffer = []
    edge_buffer = []
    batch_size = 100 # Bulk-flushing limits
    article_count = 0
    text_limit = 800
    
    for row in dataset:
        text_payload = row.get("text", "").strip()
        
        # Skip empty layout elements or short headers
        if not text_payload or len(text_payload) < 200 or text_payload.startswith("="):
            continue

        if article_count >= max_articles:
            break
            
        article_count += 1
            
        chunk_id = f"wiki_node_{article_count}"
        title = text_payload.split("\n")[0].replace("=", "").strip()[:50]
        truncated_text = text_payload[:text_limit]
        
        # A. Execute Batch Local Vector Calculation Matrix
        vector = embedding_model.encode(truncated_text).tolist()
        
        # B. Parse Structural Named Entities via spaCy Engine
        doc = nlp(truncated_text)
        entities = list(set([
            ent.text.strip() for ent in doc.ents 
            if ent.label_ in ['ORG', 'PERSON', 'GPE'] and len(ent.text.strip()) > 2
        ]))
        
        # C. Buffer raw document metadata entries
        chunk_buffer.append({
            "chunk_id": chunk_id,
            "title": title if title else f"Wikipedia Article {article_count}",
            "text_content": truncated_text,
            "vector_embedding": vector,
            "extracted_entities": entities
        })
        
        # D. Buffer structural network adjacency tracking paths
        for entity in entities:
            edge_buffer.append({
                "source": chunk_id,
                "target": entity,
                "relationship_type": "CONTAINS"
            })
            
        # If write limits are met, perform an atomic bulk array flush to MongoDB
        if len(chunk_buffer) >= batch_size:
            chunks_col.insert_many(chunk_buffer)
            if edge_buffer:
                edges_col.insert_many(edge_buffer)
            print(f"  📦 Flushed bulk batch database block. Total files indexed: {article_count}")
            chunk_buffer.clear()
            edge_buffer.clear()
            
    # Clean out trailing metrics remaining in array buffers
    if chunk_buffer:
        chunks_col.insert_many(chunk_buffer)
        if edge_buffer:
            edges_col.insert_many(edge_buffer)
        chunk_buffer.clear()
        edge_buffer.clear()

    print(f"\n⚡ Ingestion finished successfully. Processing {article_count} files into network graph webs...")
    execute_vector_cascade(chunks_col, edges_col, threshold=0.55)
    return article_count

def execute_vector_cascade(chunks_col, edges_col, threshold):
    chunks = list(chunks_col.find({}, {"chunk_id": 1, "vector_embedding": 1}))
    if len(chunks) < 2:
        return

    vectors = np.asarray([chunk["vector_embedding"] for chunk in chunks], dtype=np.float32)
    similarities = cosine_similarity(vectors)
    bridges_built = 0
    edge_bulk = []
    
    for i in range(len(chunks)):
        for offset in np.flatnonzero(similarities[i, i + 1:] >= threshold):
            j = i + 1 + int(offset)
            similarity = float(similarities[i, j])
            if similarity >= threshold:
                edge_bulk.append({
                    "source": chunks[i]["chunk_id"], 
                    "target": chunks[j]["chunk_id"],
                    "relationship_type": "CROSS_ARTICLE_SEMANTIC_BRIDGE", 
                    "weight": similarity
                })
                bridges_built += 1

                if len(edge_bulk) >= 1000:
                    edges_col.insert_many(edge_bulk)
                    edge_bulk.clear()
                
    if edge_bulk:
        edges_col.insert_many(edge_bulk)
        
    print(f"🕸️ Graph Cascade Complete! Injected {bridges_built} cross-document context paths into MongoDB.")
