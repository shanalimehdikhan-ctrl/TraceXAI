import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=API_KEY)

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge_base"
CHROMA_DIR = BASE_DIR / "data" / "chroma"

COLLECTION_NAME = "tracex_knowledge"


# ---------------------------------------------------------
# 2. CHROMA
# ---------------------------------------------------------
chroma_client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)

collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"description": "TraceX AI knowledge base"}
)


# ---------------------------------------------------------
# 3. LOAD KNOWLEDGE DOCUMENTS
# ---------------------------------------------------------
def load_documents():
    documents = []

    for path in KNOWLEDGE_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            text = path.read_text(encoding="utf-8").strip()

            if text:
                documents.append(
                    {
                        "id": path.stem,
                        "source": path.name,
                        "text": text,
                    }
                )

    return documents


# ---------------------------------------------------------
# 4. CREATE EMBEDDINGS
# ---------------------------------------------------------
def create_embeddings(texts):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )

    return [embedding.values for embedding in response.embeddings]


# ---------------------------------------------------------
# 5. BUILD / UPDATE KNOWLEDGE BASE
# ---------------------------------------------------------
def build_knowledge_base():

    documents = load_documents()

    if not documents:
        raise ValueError(
            "No .md or .txt files found in data/knowledge_base"
        )

    texts = [item["text"] for item in documents]
    embeddings = create_embeddings(texts)

    collection.upsert(
        ids=[item["id"] for item in documents],
        documents=texts,
        embeddings=embeddings,
        metadatas=[
            {"source": item["source"]}
            for item in documents
        ],
    )

    print("\n========================================")
    print("TRACEX AI - KNOWLEDGE BASE")
    print("========================================")
    print(f"Documents indexed: {len(documents)}")
    print(f"Chroma collection: {COLLECTION_NAME}")
    print(f"Storage: {CHROMA_DIR}")
    print("\n✅ Knowledge base built successfully.")


# ---------------------------------------------------------
# 6. LOCAL TEST
# ---------------------------------------------------------
if __name__ == "__main__":
    build_knowledge_base()