import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ---------------------------------------------------------
# 1. ENVIRONMENT
# ---------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=API_KEY)


# ---------------------------------------------------------
# 2. PATHS
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "data" / "chroma"

COLLECTION_NAME = "tracex_knowledge"


# ---------------------------------------------------------
# 3. CHROMA COLLECTION
# ---------------------------------------------------------
chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)

collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME
)


# ---------------------------------------------------------
# 4. QUERY EMBEDDING
# ---------------------------------------------------------
def create_query_embedding(query: str):

    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=query,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768,
        ),
    )

    return response.embeddings[0].values


# ---------------------------------------------------------
# 5. RETRIEVE RELEVANT KNOWLEDGE
# ---------------------------------------------------------
def retrieve_knowledge(query: str, n_results: int = 3):

    query_embedding = create_query_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
    )

    retrieved = []

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for document, metadata, distance in zip(
        documents,
        metadatas,
        distances,
    ):
        retrieved.append(
            {
                "document": document,
                "source": metadata.get("source", "unknown"),
                "distance": distance,
            }
        )

    return retrieved


# ---------------------------------------------------------
# 6. LOCAL TEST
# ---------------------------------------------------------
if __name__ == "__main__":

    query = """
    What evidence should be available to connect a supplier,
    material and finished product?
    """

    results = retrieve_knowledge(query)

    print("\n========================================")
    print("TRACEX AI - RAG RETRIEVER")
    print("========================================\n")

    for index, item in enumerate(results, start=1):

        print(f"RESULT {index}")
        print(f"Source: {item['source']}")
        print(f"Distance: {item['distance']:.4f}")
        print("-" * 60)
        print(item["document"][:600])
        print("-" * 60)
        print()

    print("✅ RAG retrieval test completed.")