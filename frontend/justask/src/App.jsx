import { useState, useEffect, useRef, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Routes, Route, useLocation } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import toast from 'react-hot-toast'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload, FileText, Send, Sparkles, Trash2,
  MessageSquare, Clock, Zap, Bot, User,
  CheckCircle, Loader, XCircle, ArrowLeft, Trash, Sun, Moon
} from 'lucide-react'
import {
  uploadDocument, listDocuments, deleteDocument,
  streamQuery, getHealth
} from './services/api'
import LandingPage from './LandingPage'
import './App.css'

const MAX_MESSAGES = 50

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => sessionStorage.getItem('justask_auth') === 'true')

  // ── State ─────────────────────────────────────────────────────────
  const [documents, setDocuments] = useState([])
  const [allMessages, setAllMessages] = useState({}) // { docId: [messages] }
  const [selectedDocId, setSelectedDocId] = useState(null)
  
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [healthStatus, setHealthStatus] = useState('checking')
  const [theme, setTheme] = useState(() => localStorage.getItem('justask_theme') || 'light')
  const [confirmDialog, setConfirmDialog] = useState({ isOpen: false, title: '', message: '', onConfirm: null })
  
  const chatEndRef = useRef(null)
  const inputRef = useRef(null)

  // ── Effects ───────────────────────────────────────────────────────
  useEffect(() => {
    loadDocuments()
    checkHealth()
    const savedChats = localStorage.getItem('justask_chats')
    if (savedChats) {
      try { setAllMessages(JSON.parse(savedChats)) } catch(e) { console.error(e) }
    }
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('justask_theme', theme)
  }, [theme])

  useEffect(() => {
    if (selectedDocId) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [allMessages, selectedDocId])

  // ── API Calls ─────────────────────────────────────────────────────
  async function loadDocuments() {
    try {
      const data = await listDocuments()
      setDocuments(data.documents || [])
    } catch {
      /* Backend not ready yet */
    }
  }

  async function checkHealth() {
    try {
      const data = await getHealth()
      setHealthStatus(data.status)
    } catch {
      setHealthStatus('unhealthy')
    }
  }

  // ── File Upload ───────────────────────────────────────────────────
  const onDrop = useCallback(async (acceptedFiles) => {
    for (const file of acceptedFiles) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        toast.error(`"${file.name}" is not a PDF file`)
        continue
      }

      const toastId = toast.loading(`Uploading ${file.name}...`)
      try {
        await uploadDocument(file)
        toast.success(`"${file.name}" uploaded! Processing...`, { id: toastId })
        loadDocuments()

        const pollInterval = setInterval(async () => {
          await loadDocuments()
        }, 3000)
        setTimeout(() => clearInterval(pollInterval), 60000)
      } catch (err) {
        toast.error(err.message || 'Upload failed', { id: toastId })
      }
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  })

  // ── Delete Document ───────────────────────────────────────────────
  const closeConfirmDialog = () => setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null })

  function handleDeleteDocument(id, name, e) {
    e.stopPropagation()
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Document',
      message: `Are you sure you want to delete "${name}"? This action cannot be undone.`,
      onConfirm: async () => {
        closeConfirmDialog()
        try {
          await deleteDocument(id)
          toast.success(`"${name}" deleted`)
          if (selectedDocId === id) setSelectedDocId(null)
          
          // Cleanup chat history
          setAllMessages(prev => {
            const next = { ...prev }
            delete next[id]
            localStorage.setItem('justask_chats', JSON.stringify(next))
            return next
          })
          
          loadDocuments()
        } catch (err) {
          toast.error(err.message || 'Delete failed')
        }
      }
    })
  }

  // ── Clear Chat ────────────────────────────────────────────────────
  function handleClearChat() {
    if (!selectedDocId) return
    setConfirmDialog({
      isOpen: true,
      title: 'Clear Chat History',
      message: 'Are you sure you want to clear the chat history for this document?',
      onConfirm: () => {
        closeConfirmDialog()
        setAllMessages(prev => {
          const next = { ...prev }
          delete next[selectedDocId]
          localStorage.setItem('justask_chats', JSON.stringify(next))
          return next
        })
      }
    })
  }

  // ── Send Query ────────────────────────────────────────────────────
  async function handleSendQuery(queryText) {
    const query = (queryText || inputValue).trim()
    if (!query || isLoading || !selectedDocId) return

    setInputValue('')
    setIsLoading(true)

    const userMsg = { role: 'user', content: query, timestamp: new Date() }
    const assistantMsg = {
      role: 'assistant', content: '', sources: [], latency_ms: null,
      timestamp: new Date(), isStreaming: true
    }

    setAllMessages(prev => {
      let docMsgs = prev[selectedDocId] || []
      docMsgs = [...docMsgs, userMsg, assistantMsg]
      if (docMsgs.length > MAX_MESSAGES) docMsgs = docMsgs.slice(-MAX_MESSAGES)
      const next = { ...prev, [selectedDocId]: docMsgs }
      localStorage.setItem('justask_chats', JSON.stringify(next))
      return next
    })

    const historyToSend = (allMessages[selectedDocId] || [])
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }));

    try {
      await streamQuery(
        query, 5, selectedDocId === 'global' ? null : [selectedDocId], historyToSend,
        (token) => {
          setAllMessages(prev => {
            const next = { ...prev }
            const docMsgs = [...(next[selectedDocId] || [])]
            const last = docMsgs[docMsgs.length - 1]
            if (last && last.role === 'assistant') {
              docMsgs[docMsgs.length - 1] = { ...last, content: last.content + token }
            }
            next[selectedDocId] = docMsgs
            return next
          })
        },
        (data) => {
          setAllMessages(prev => {
            const next = { ...prev }
            const docMsgs = [...(next[selectedDocId] || [])]
            const last = docMsgs[docMsgs.length - 1]
            if (last && last.role === 'assistant') {
              docMsgs[docMsgs.length - 1] = {
                ...last, sources: data.sources || [], latency_ms: data.latency_ms, isStreaming: false
              }
            }
            next[selectedDocId] = docMsgs
            localStorage.setItem('justask_chats', JSON.stringify(next))
            return next
          })
          setIsLoading(false)
        },
        (error) => {
          setAllMessages(prev => {
            const next = { ...prev }
            const docMsgs = [...(next[selectedDocId] || [])]
            const last = docMsgs[docMsgs.length - 1]
            if (last && last.role === 'assistant') {
              docMsgs[docMsgs.length - 1] = {
                ...last, content: `Sorry, an error occurred: ${error}`, isStreaming: false
              }
            }
            next[selectedDocId] = docMsgs
            localStorage.setItem('justask_chats', JSON.stringify(next))
            return next
          })
          setIsLoading(false)
          toast.error(error)
        }
      )
    } catch (err) {
      setAllMessages(prev => {
        const next = { ...prev }
        const docMsgs = [...(next[selectedDocId] || [])]
        const last = docMsgs[docMsgs.length - 1]
        if (last && last.role === 'assistant') {
          docMsgs[docMsgs.length - 1] = {
            ...last, content: `Sorry, I couldn't process your question. ${err.message || 'Please try again.'}`, isStreaming: false
          }
        }
        next[selectedDocId] = docMsgs
        localStorage.setItem('justask_chats', JSON.stringify(next))
        return next
      })
      setIsLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendQuery()
    }
  }

  // ── Format file size ──────────────────────────────────────────────
  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function StatusIcon({ status }) {
    switch (status) {
      case 'completed': return <CheckCircle size={12} />
      case 'processing': return <Loader size={12} className="spinning" />
      case 'failed': return <XCircle size={12} />
      default: return <Clock size={12} />
    }
  }

  const activeDoc = selectedDocId === 'global' 
    ? { id: 'global', original_filename: 'All Documents', filename: 'All Documents' } 
    : documents.find(d => d.id === selectedDocId)
  const currentMessages = selectedDocId ? (allMessages[selectedDocId] || []) : []
  const location = useLocation()

  if (!isAuthenticated) {
    return (
      <div className="password-gate">
        <motion.div 
          className="password-gate-card"
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
        >
          <div className="password-gate-icon">
            <Zap size={32} color="var(--accent)" />
          </div>
          <h2>Just Ask</h2>
          <p>Please enter the portfolio password to view the project.</p>
          <form onSubmit={(e) => {
            e.preventDefault()
            const pw = e.target.password.value
            if (pw === 'hireme2026') {
              sessionStorage.setItem('justask_auth', 'true')
              setIsAuthenticated(true)
            } else {
              toast.error('Incorrect password')
            }
          }}>
            <input type="password" name="password" placeholder="Password" autoFocus />
            <button type="submit">Access</button>
          </form>
        </motion.div>
      </div>
    )
  }

  // Main app content (extracted so we can wrap it in a route)
  const appContent = (
    <motion.div
      className="app"
      key="app"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      {/* ── Sidebar ────────────────────────────────────────────────── */}
      <aside className="sidebar" id="sidebar">
        <div className="sidebar-header" onClick={() => setSelectedDocId(null)} style={{ cursor: 'pointer' }}>
          <div className="sidebar-logo">
            <Zap size={18} />
          </div>
          <div>
            <div className="sidebar-title">Just Ask</div>
            <div className="sidebar-subtitle">AI Document Assistant</div>
          </div>
        </div>

        {/* Upload Zone */}
        <div
          {...getRootProps()}
          className={`upload-zone ${isDragActive ? 'drag-active' : ''}`}
          id="upload-zone"
        >
          <input {...getInputProps()} id="file-input" />
          <div className="upload-zone-icon">
            <Upload size={24} />
          </div>
          <div className="upload-zone-text">
            <strong>Drop PDFs here</strong>
          </div>
          <div className="upload-zone-hint">Max 50MB per file</div>
        </div>

        {/* Document List */}
        <div className="doc-list-header">
          <span>Global Knowledge Base</span>
        </div>
        <div 
          className={`doc-item ${selectedDocId === 'global' ? 'active' : ''}`}
          onClick={() => setSelectedDocId('global')}
          style={{ margin: '0 8px 16px', background: selectedDocId === 'global' ? 'var(--accent)' : 'var(--surface-elevated)', color: selectedDocId === 'global' ? 'var(--text-accent)' : 'inherit' }}
        >
          <div className="doc-item-icon" style={{ background: selectedDocId === 'global' ? 'rgba(255,255,255,0.2)' : 'var(--accent-subtle)', color: selectedDocId === 'global' ? '#fff' : 'var(--accent)' }}>
            <Sparkles size={16} />
          </div>
          <div className="doc-item-info">
            <div className="doc-item-name">Chat with All Documents</div>
          </div>
        </div>

        <div className="doc-list-header">
          <span>Your Documents</span>
          <span className="doc-list-count">{documents.length}</span>
        </div>

        <div className="doc-list" id="document-list">
          {documents.length === 0 ? (
            <div className="doc-empty-state">
              No documents uploaded yet
            </div>
          ) : (
            documents.map(doc => (
              <div 
                key={doc.id} 
                className={`doc-item ${selectedDocId === doc.id ? 'active' : ''}`}
                onClick={() => setSelectedDocId(doc.id)}
              >
                <div className="doc-item-icon">
                  <FileText size={16} />
                </div>
                <div className="doc-item-info">
                  <div className="doc-item-name" title={doc.original_filename || doc.filename}>
                    {doc.original_filename || doc.filename}
                  </div>
                  <div className="doc-item-meta">
                    <span className={`doc-item-status ${doc.status}`}>
                      <StatusIcon status={doc.status} />
                      {doc.status}
                    </span>
                  </div>
                </div>
                <button
                  className="doc-item-delete"
                  onClick={(e) => handleDeleteDocument(doc.id, doc.original_filename || doc.filename, e)}
                  title="Delete document"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* ── Main Content ──────────────────────────────────────────── */}
      <main className="main-content">
        {/* Header */}
        <header className="main-header">
          <div className="main-header-left">
            {selectedDocId ? (
              <div className="chat-header-title">
                <button className="back-btn" onClick={() => setSelectedDocId(null)}>
                  <ArrowLeft size={18} />
                </button>
                <div className="chat-header-info">
                  <h2>{activeDoc?.original_filename || activeDoc?.filename || 'Chat'}</h2>
                </div>
              </div>
            ) : (
              <div className="main-header-title">
                <h1>Dashboard</h1>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <motion.button
              className="theme-toggle-btn"
              onClick={() => setTheme(prev => prev === 'light' ? 'dark' : 'light')}
              style={{
                background: 'var(--surface)',
                border: 'var(--border-width) solid var(--border)',
                borderRadius: 'var(--radius-md)',
                width: '36px', height: '36px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)'
              }}
              title="Toggle Theme"
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9, rotate: 180 }}
              transition={{ duration: 0.3 }}
            >
              <AnimatePresence mode="wait">
                <motion.div
                  key={theme}
                  initial={{ rotate: -90, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={{ rotate: 90, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {theme === 'light' ? <Moon size={18} color="var(--text-primary)" /> : <Sun size={18} color="var(--text-primary)" />}
                </motion.div>
              </AnimatePresence>
            </motion.button>
            <div className="health-indicator">
              <span className={`health-dot ${healthStatus}`} />
              <span>
                {healthStatus === 'healthy' ? 'All systems operational' :
                 healthStatus === 'degraded' ? 'Partially available' :
                 healthStatus === 'checking' ? 'Connecting...' :
                 'Backend offline'}
              </span>
            </div>
          </div>
        </header>

        {/* View Routing */}
        {!selectedDocId ? (
          /* ── Home Page Dashboard ── */
          <motion.div 
            className="home-dashboard"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
          >
            <div className="hero-section">
              <motion.div 
                className="hero-icon"
                initial={{ scale: 0, rotate: -180 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.1 }}
              >
                <Sparkles size={48} />
              </motion.div>
              <motion.h1 
                className="hero-title"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.5 }}
              >
                Welcome to Just Ask
              </motion.h1>
              <motion.p 
                className="hero-subtitle"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.5 }}
              >
                Your secure, AI-powered knowledge base. Upload PDF documents and interact with them instantly. Our advanced Retrieval-Augmented Generation (RAG) pipeline ensures that every answer is accurate, contextual, and fully cited from your own data.
              </motion.p>
            </div>
            
            <motion.div 
              className="dashboard-grid"
              initial="hidden"
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: {
                  opacity: 1,
                  transition: {
                    staggerChildren: 0.1,
                    delayChildren: 0.4
                  }
                }
              }}
            >
              {/* Global Chat Card */}
              <motion.div 
                className="dash-card" 
                onClick={() => setSelectedDocId('global')}
                style={{ background: 'var(--accent)' }}
                variants={{
                  hidden: { opacity: 0, y: 40 },
                  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } }
                }}
              >
                <div className="dash-card-icon" style={{ background: 'rgba(255,255,255,0.2)', color: 'var(--text-accent)' }}>
                  <Sparkles size={32} />
                </div>
                <div className="dash-card-content">
                  <h3 style={{ color: 'var(--text-accent)' }}>Global Chat</h3>
                  <p style={{ color: 'rgba(255,255,255,0.8)' }}>Chat with all your {documents.length} documents at once</p>
                </div>
                <div className="dash-card-action" style={{ color: 'var(--text-accent)' }}>
                  <MessageSquare size={16} />
                  <span>Chat</span>
                </div>
              </motion.div>

              {documents.map(doc => (
                <motion.div 
                  key={doc.id} 
                  className="dash-card" 
                  onClick={() => setSelectedDocId(doc.id)}
                  variants={{
                    hidden: { opacity: 0, y: 40 },
                    visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } }
                  }}
                >
                  <div className="dash-card-icon">
                    <FileText size={32} />
                  </div>
                  <div className="dash-card-content">
                    <h3>{doc.original_filename || doc.filename}</h3>
                    <p>{formatSize(doc.file_size_bytes)} • {doc.total_chunks || 0} chunks</p>
                  </div>
                  <div className="dash-card-action">
                    <MessageSquare size={16} />
                    <span>Chat</span>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        ) : (
          /* ── Chat View ── */
          <>
            <div className="chat-area" id="chat-area">
              {currentMessages.length === 0 ? (
                <div className="chat-empty">
                  <div className="chat-empty-icon">
                    <MessageSquare size={36} color="white" />
                  </div>
                  <h2>Chat with {activeDoc?.original_filename || activeDoc?.filename}</h2>
                  <p>Ask anything about this specific document. Your chat history is saved locally.</p>
                  <div className="chat-empty-suggestions">
                    {["Summarize this document", "What are the key findings?", "List the main entities"].map((s, i) => (
                      <button key={i} className="suggestion-chip" onClick={() => {
                        setInputValue(s)
                        inputRef.current?.focus()
                      }}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                currentMessages.map((msg, i) => (
                  <div key={i} className={`chat-message ${msg.role}`} id={`msg-${i}`}>
                    <div className={`message-avatar ${msg.role}`}>
                      {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                    </div>
                    <div>
                      <div className={`message-content ${msg.role}`}>
                        {msg.role === 'assistant' ? (
                          <>
                            {msg.content ? (
                              <ReactMarkdown>{msg.content}</ReactMarkdown>
                            ) : msg.isStreaming ? (
                              <div className="typing-indicator">
                                <div className="typing-dot" />
                                <div className="typing-dot" />
                                <div className="typing-dot" />
                              </div>
                            ) : null}
                          </>
                        ) : (
                          msg.content
                        )}
                      </div>

                      {msg.sources && msg.sources.length > 0 && (
                        <div className="message-sources">
                          <div className="message-sources-title">Sources ({msg.sources.length})</div>
                          {msg.sources.map((src, j) => (
                            <div key={j} className="source-card">
                              <span className="source-page">Page {src.page_number}</span>
                              <div className="source-info">
                                <div className="source-snippet">{src.snippet}</div>
                              </div>
                              <span className="source-score">{(src.relevance_score * 100).toFixed(0)}%</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {msg.role === 'assistant' && msg.latency_ms && !msg.isStreaming && (
                        <div className="message-meta">
                          <span><Clock size={10} /> {msg.latency_ms.toFixed(0)}ms</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="chat-input-container">
              <div className="chat-input-wrapper">
                <button className="clear-chat-btn" onClick={handleClearChat} title="Clear Chat History">
                  <Trash size={16} />
                </button>
                <textarea
                  ref={inputRef}
                  className="chat-input"
                  placeholder={`Ask a question about ${activeDoc?.original_filename || activeDoc?.filename || 'this document'}...`}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  id="query-input"
                  disabled={isLoading}
                />
                <button
                  className="send-button"
                  onClick={() => handleSendQuery()}
                  disabled={!inputValue.trim() || isLoading}
                  id="send-button"
                >
                  {isLoading ? <div className="spinner" /> : <Send size={16} />}
                </button>
              </div>
              <div className="chat-input-hint">
                Press Enter to send · Shift+Enter for new line
              </div>
            </div>
          </>
        )}
      </main>

      {/* ── Confirmation Modal ── */}
      <AnimatePresence>
        {confirmDialog.isOpen && (
          <div className="modal-overlay" onClick={closeConfirmDialog}>
            <motion.div 
              className="modal-content"
              onClick={e => e.stopPropagation()}
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
            >
              <h3>{confirmDialog.title}</h3>
              <p>{confirmDialog.message}</p>
              <div className="modal-actions">
                <button className="modal-btn cancel" onClick={closeConfirmDialog}>Cancel</button>
                <button className="modal-btn confirm" onClick={confirmDialog.onConfirm}>Confirm</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  )

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/upload" element={appContent} />
      </Routes>
    </AnimatePresence>
  )
}

export default App

