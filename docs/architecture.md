# System Architecture

Just Ask is built using a modern, decoupled architecture featuring a React frontend and an asynchronous FastAPI backend. The system leverages Retrieval-Augmented Generation (RAG) to provide grounded, accurate answers from user-uploaded PDFs.

## High-Level Data Flow

1. **Document Ingestion**:
   - A user uploads a PDF via the React UI.
   - The FastAPI backend validates the file and uploads it to local storage.
   - A background task is dispatched using FastAPI `BackgroundTasks`.
   - `PyPDF` extracts text from the document.
   - The text is chunked into overlapping segments (default 1000 characters, 200 overlap).
   - `SentenceTransformers` (`all-MiniLM-L6-v2`) converts these chunks into vector embeddings.
   - Embeddings and metadata are stored locally in **ChromaDB**.
   - Document state is updated in the SQL Database.

2. **Querying (RAG)**:
   - User asks a question in an isolated document chat.
   - Backend performs a **Hybrid Search**:
     - Vector similarity search via ChromaDB.
     - Keyword search via BM25.
   - The top `K` most relevant chunks are retrieved.
   - The chunks and the user's query are packed into a prompt.
   - The prompt is sent to **Groq Cloud** (`llama-3.3-70b-versatile`) via asynchronous HTTP requests (`httpx`).
   - The LLM streams the answer back to the backend.
   - The backend proxies the streaming response to the frontend using Server-Sent Events (SSE).

## Component Breakdown

### Frontend (`frontend/justask/`)
- **React 19**: Manages the UI view layer.
- **State Management**: React `useState` and `useEffect` manage the View routing (Dashboard vs Chat) without a heavy router library.
- **Memory Management**: `localStorage` serializes and stores up to 50 recent messages per document.
- **Styling**: Pure CSS with CSS Variables to enforce a design system and glassmorphism UI.

### Backend (`backend/`)
- **API Layer (`app/api/`)**: Defines the REST endpoints for Chat and Documents.
- **Core (`app/core/`)**: 
  - `settings.py`: Pydantic-based configuration management.
  - `middleware.py`: CORS and Proxy headers.
  - `logging.py`: Structured JSON and Console logging via `loguru`.
  - `dependencies.py`: FastAPI Dependency Injection for services.
- **Services (`app/services/`)**:
  - `vector_db.py`: Wrapper for ChromaDB operations.
  - `embedding_service.py`: Local HuggingFace transformer wrapper with LRU caching.
  - `llm_service.py`: API client for Groq Cloud.
  - `pdf_parser.py`: PyPDF extraction and LangChain-style recursive character text splitting.
  - `rag_service.py`: Orchestrator that bridges search, context compilation, and LLM invocation.
- **Database (`app/database/`)**: Asynchronous SQLAlchemy 2.0 with connection pooling.

## Scalability Considerations
- **Stateless API**: The FastAPI backend is entirely stateless (except for local ChromaDB files in development). In a multi-node production setup, ChromaDB should be replaced with a managed vector database (like Pinecone or pgvector).
- **Asynchronous I/O**: The backend uses `asyncio` exclusively for database calls and LLM HTTP requests, preventing thread blocking during long inferences.
