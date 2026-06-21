# API Reference

The backend exposes a RESTful JSON API documented automatically by FastAPI. When running the server locally, you can view the interactive Swagger documentation at `http://localhost:8000/docs`.

## Base URL
`/api/v1`

---

## 1. Documents API

### `POST /documents/upload`
Uploads a PDF and initiates background processing (parsing, chunking, vector embedding).
- **Content-Type**: `multipart/form-data`
- **Body**: `file` (PDF file binary)
- **Response**: `DocumentUploadResponse` (202 Accepted)

### `GET /documents`
List all uploaded documents with pagination.
- **Query Params**: `page` (int, default=1), `page_size` (int, default=20)
- **Response**: `DocumentListResponse`

### `GET /documents/{id}`
Get detailed metadata for a specific document.
- **Response**: `DocumentResponse`

### `DELETE /documents/{id}`
Deletes a document from the SQL database and removes its embeddings from ChromaDB.

---

## 2. Chat API

### `POST /chat/query`
Ask a natural language question about uploaded documents. The backend uses Hybrid Search to retrieve relevant context.
- **Content-Type**: `application/json`
- **Body**: 
  ```json
  {
    "query": "What is the patient's age?",
    "top_k": 5,
    "document_ids": [1] 
  }
  ```
  *(Note: `document_ids` is an optional array to isolate the search space. If null, it searches all documents).*
- **Response**: `ChatResponse` (includes the answer text, latency, and a list of citation source chunks).

### `POST /chat/stream`
Same as `/query`, but returns a Server-Sent Events (SSE) stream.
- **Content-Type**: `application/json`
- **Response**: `text/event-stream`
- **Stream Format**: Each token is yielded as a JSON payload: `data: {"token": "Hello"}`. The final chunk contains `{"done": true, "sources": [...]}`.

### `GET /chat/history`
Returns paginated list of past queries and responses.

---

## 3. System API

### `GET /health`
Basic service health check (Database, Vector DB, LLM Service).

### `GET /health/live`
Fast, lightweight endpoint for Load Balancer / Render liveness probes. Returns `{"status": "ok"}`.
