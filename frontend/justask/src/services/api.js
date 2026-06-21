/**
 * API service layer — all backend communication goes through here.
 *
 * Centralizes: base URL, error handling, response parsing.
 */

// In production, VITE_API_URL should be set to the backend's full URL (e.g., https://justask-api.onrender.com/api/v1)
// In development, falls back to localhost
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

class ApiError extends Error {
  constructor(status, errorCode, message, detail) {
    super(message);
    this.status = status;
    this.errorCode = errorCode;
    this.detail = detail;
  }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  // Remove Content-Type for FormData (browser sets it with boundary)
  if (config.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { message: `HTTP ${response.status}` };
      }
      throw new ApiError(
        response.status,
        errorData.error_code || 'UNKNOWN',
        errorData.message || `Request failed with status ${response.status}`,
        errorData.detail
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, 'NETWORK_ERROR', 'Unable to connect to the server. Is the backend running?');
  }
}

// ── Documents API ──────────────────────────────────────────────────────

export async function uploadDocument(file, onProgress) {
  const formData = new FormData();
  formData.append('file', file);

  return request('/documents/upload', {
    method: 'POST',
    body: formData,
  });
}

export async function listDocuments(page = 1, pageSize = 50) {
  return request(`/documents?page=${page}&page_size=${pageSize}`);
}

export async function getDocument(id) {
  return request(`/documents/${id}`);
}

export async function getDocumentStatus(id) {
  return request(`/documents/${id}/status`);
}

export async function deleteDocument(id) {
  return request(`/documents/${id}`, { method: 'DELETE' });
}

// ── Chat API ───────────────────────────────────────────────────────────

export async function queryDocuments(query, topK = 5, documentIds = null) {
  const body = { query, top_k: topK };
  if (documentIds) body.document_ids = documentIds;

  return request('/chat/query', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function streamQuery(query, topK = 5, documentIds = null, onToken, onDone, onError) {
  const body = { query, top_k: topK };
  if (documentIds) body.document_ids = documentIds;

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        errorData.error_code || 'STREAM_ERROR',
        errorData.message || 'Streaming failed'
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.error) {
            onError?.(data.error);
            return;
          }
          if (data.done) {
            onDone?.(data);
          } else {
            onToken?.(data.token);
          }
        } catch { /* skip malformed chunks */ }
      }
    }
  } catch (error) {
    onError?.(error.message || 'Stream connection failed');
  }
}

export async function getQueryHistory(page = 1, pageSize = 20) {
  return request(`/chat/history?page=${page}&page_size=${pageSize}`);
}

// ── Health API ─────────────────────────────────────────────────────────

export async function getHealth() {
  return request('/health');
}

// ── Admin API ──────────────────────────────────────────────────────────

export async function getSystemStats() {
  return request('/admin/stats');
}

export { ApiError };
