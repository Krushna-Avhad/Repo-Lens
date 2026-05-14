import { useState, useRef, useEffect, useCallback } from 'react'
import { useStore } from '../store'
import axios from 'axios'
import {
  Send, Loader2, User, Bot, Zap, Wrench, Bug, MessageSquare,
  ChevronRight, Network, CheckCircle2, Circle, Cpu
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import toast from 'react-hot-toast'

const AGENT_META = {
  explanation: { icon: MessageSquare, color: '#00d4aa', label: 'Explain Agent' },
  impact:      { icon: Zap,           color: '#7c3aed', label: 'Impact Agent' },
  refactor:    { icon: Wrench,        color: '#f59e0b', label: 'Refactor Agent' },
  debug:       { icon: Bug,           color: '#ef4444', label: 'Debug Agent' },
}

const PIPELINE_STEPS = [
  { id: 'intent',    label: 'Intent classification' },
  { id: 'cypher',    label: 'Cypher generation' },
  { id: 'execute',   label: 'Graph execution' },
  { id: 'expand',    label: 'Subgraph expansion' },
  { id: 'vector',    label: 'Vector search (FAISS)' },
  { id: 'fuse',      label: 'RRF fusion' },
  { id: 'summarise', label: 'Context summarisation' },
  { id: 'answer',    label: 'Groq answer generation' },
]

const QUICK_PROMPTS = {
  explanation: ['How does authentication work?', 'Explain the main architecture', 'What are the API endpoints?'],
  impact:      ['What breaks if I change the auth service?', 'Impact of removing the database module?', 'Dependencies of the main entry point?'],
  refactor:    ['Find code smells and circular dependencies', 'Detect tight coupling', 'Suggest modularisation'],
  debug:       ['Why might login fail?', 'Trace the request lifecycle', 'What causes timeout errors?'],
}

// ── Pipeline tracker component ─────────────────────────────────────────────
function PipelineTracker({ steps, activeStep, done }) {
  return (
    <div className="rounded-xl p-3 mb-3 animate-fade-in"
      style={{ background: '#0d0f14', border: '1px solid #1e2230' }}>
      <div className="flex items-center gap-2 mb-2">
        <Cpu size={11} className="text-accent" />
        <span className="text-xs font-mono text-accent uppercase tracking-widest">Graph RAG Pipeline</span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {PIPELINE_STEPS.map((step, i) => {
          const stepIdx = PIPELINE_STEPS.findIndex(s => s.id === activeStep)
          const isDone    = done || i < stepIdx
          const isActive  = step.id === activeStep && !done
          return (
            <div key={step.id} className="flex items-center gap-1.5 py-0.5">
              {isDone
                ? <CheckCircle2 size={10} className="text-accent shrink-0" />
                : isActive
                  ? <div className="w-2.5 h-2.5 rounded-full bg-accent animate-pulse-slow shrink-0" />
                  : <Circle size={10} className="text-muted shrink-0" />}
              <span className="text-xs font-mono truncate"
                style={{ color: isDone ? '#00d4aa' : isActive ? '#e2e8f0' : '#4b5563' }}>
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Meta badge shown after Graph RAG response ──────────────────────────────
function GraphRAGMeta({ meta }) {
  if (!meta) return null
  return (
    <div className="flex flex-wrap gap-2 mt-2 pt-2 border-t border-border">
      {[
        { label: 'Nodes',     val: meta.subgraph_nodes,   color: '#00d4aa' },
        { label: 'Edges',     val: meta.subgraph_edges,   color: '#7c3aed' },
        { label: 'Vectors',   val: meta.vector_hits,      color: '#3b82f6' },
        { label: 'Confidence',val: meta.confidence ? `${Math.round(meta.confidence * 100)}%` : '—', color: '#f59e0b' },
      ].map(b => (
        <span key={b.label} className="flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded"
          style={{ background: '#0d0f14', border: '1px solid #1e2230', color: b.color }}>
          {b.label}: {b.val ?? '—'}
        </span>
      ))}
      {meta.intent?.intent && (
        <span className="text-xs font-mono px-2 py-0.5 rounded"
          style={{ background: '#0d0f14', border: '1px solid #1e2230', color: '#94a3b8' }}>
          intent: {meta.intent.intent}
        </span>
      )}
      {meta.cypher_used && meta.cypher_used !== 'FALLBACK' && (
        <details className="w-full mt-1">
          <summary className="text-xs font-mono text-muted cursor-pointer hover:text-accent">
            View Cypher query ↓
          </summary>
          <pre className="text-xs font-mono mt-1 p-2 rounded overflow-x-auto"
            style={{ background: '#0d0f14', border: '1px solid #1e2230', color: '#00d4aa' }}>
            {meta.cypher_used}
          </pre>
        </details>
      )}
    </div>
  )
}

// ── Single message ──────────────────────────────────────────────────────────
function Message({ msg, onSuggestion }) {
  const meta    = AGENT_META[msg.agent] || AGENT_META.explanation
  const AgentIcon = meta.icon
  const isUser  = msg.role === 'user'

  return (
    <div className={`flex gap-3 mb-5 animate-slide-up ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center mt-0.5"
        style={{
          background: isUser ? 'rgba(255,255,255,0.06)' : `rgba(0,212,170,0.08)`,
          border:     `1px solid ${isUser ? '#2a3040' : meta.color + '30'}`,
        }}>
        {isUser ? <User size={12} className="text-muted" /> : <AgentIcon size={12} style={{ color: meta.color }} />}
      </div>

      <div className={`max-w-[80%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        <span className="text-xs font-mono mb-1" style={{ color: isUser ? '#4b5563' : meta.color }}>
          {isUser ? 'you' : meta.label}
        </span>

        {/* Pipeline tracker (only while streaming) */}
        {msg.streaming && (
          <PipelineTracker steps={PIPELINE_STEPS} activeStep={msg.currentStep} done={false} />
        )}

        <div className="rounded-xl px-4 py-3 text-sm"
          style={{ background: isUser ? '#1a1d26' : '#111318', border: `1px solid ${isUser ? '#2a3040' : '#1e2230'}` }}>
          {isUser ? (
            <p className="text-text-dim">{msg.content}</p>
          ) : (
            <>
              <div className="prose-dark">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ' '}</ReactMarkdown>
              </div>
              {msg.graphMeta && <GraphRAGMeta meta={msg.graphMeta} />}
            </>
          )}
        </div>

        {/* Suggestions */}
        {msg.suggestions?.length > 0 && !msg.streaming && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {msg.suggestions.map((s, i) => (
              <button key={i} onClick={() => onSuggestion(s)}
                className="text-xs px-2 py-1 rounded flex items-center gap-1 transition-colors hover:text-accent"
                style={{ background: '#1a1d26', border: '1px solid #2a3040', color: '#64748b' }}>
                {s} <ChevronRight size={10} />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
export default function ChatInterface() {
  const { activeRepo, activeAgent, messages, addMessage } = useStore()
  const [input, setInput]   = useState('')
  const [typing, setTyping] = useState(false)
  const bottomRef           = useRef(null)
  const msgIdRef            = useRef(0)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, typing])

  const handleSend = useCallback(async (text) => {
    const question = (text || input).trim()
    if (!question) return
    if (!activeRepo) { toast.error('Select or ingest a repository first'); return }

    setInput('')
    addMessage({ role: 'user', content: question, agent: activeAgent })
    setTyping(true)

    const assistantId = ++msgIdRef.current

    // Add a placeholder streaming message
    addMessage({
      _id:         assistantId,
      role:        'assistant',
      content:     '',
      agent:       activeAgent,
      streaming:   true,
      currentStep: 'intent',
    })

    try {
      // Try streaming endpoint first
      const resp = await fetch('/api/query/stream', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ repo_id: activeRepo.repo_id, question, agent: activeAgent }),
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader  = resp.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''
      let   content = ''
      let   meta    = null

      // Update the streaming message
      const update = (patch) => {
        // Zustand doesn't have fine-grained update by id; we use a workaround
        // via a custom store action (defined below). For simplicity we re-use addMessage
        // with a sentinel to patch the last assistant message.
        useStore.setState(state => ({
          messages: state.messages.map(m =>
            m._id === assistantId ? { ...m, ...patch } : m
          )
        }))
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'step') {
              update({ currentStep: event.step, streaming: true })
            } else if (event.type === 'token') {
              content += event.content
              update({ content, streaming: true })
            } else if (event.type === 'meta') {
              meta = event
              update({ graphMeta: event })
            } else if (event.type === 'done') {
              update({
                content,
                streaming:   false,
                currentStep: null,
                graphMeta:   meta,
                suggestions: [
                  'Explore the dependency chain',
                  'Run impact analysis',
                  'Check for refactoring opportunities',
                ],
              })
            } else if (event.type === 'error') {
              throw new Error(event.message)
            }
          } catch (_) {}
        }
      }

    } catch (streamErr) {
      // Fallback: non-streaming query
      try {
        const { data } = await axios.post('/api/query', {
          repo_id:  activeRepo.repo_id,
          question,
          agent:    activeAgent,
        })
        useStore.setState(state => ({
          messages: state.messages.map(m =>
            m._id === assistantId
              ? { ...m, content: data.answer, streaming: false, suggestions: data.suggestions || [], graphMeta: data }
              : m
          )
        }))
      } catch (err) {
        toast.error('Query failed: ' + err.message)
        useStore.setState(state => ({
          messages: state.messages.filter(m => m._id !== assistantId)
        }))
      }
    } finally {
      setTyping(false)
    }
  }, [input, activeRepo, activeAgent, addMessage])

  const quickPrompts = QUICK_PROMPTS[activeAgent] || []

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 animate-fade-in">
            <div className="text-center">
              {activeRepo ? (
                <>
                  <div className="flex items-center justify-center gap-2 mb-2">
                    <Network size={14} className="text-accent" />
                    <span className="text-xs font-mono text-accent uppercase tracking-widest">Graph RAG Active</span>
                  </div>
                  <p className="text-text-dim text-sm max-w-xs">
                    Ask anything — Groq + NetworkX will traverse the graph, and answer with full Graph RAG.
                  </p>
                </>
              ) : (
                <p className="text-muted text-sm">Ingest a repository to get started</p>
              )}
            </div>
            {activeRepo && (
              <div className="flex flex-col gap-2 w-full max-w-sm">
                {quickPrompts.map(p => (
                  <button key={p} onClick={() => handleSend(p)}
                    className="text-left text-sm px-4 py-3 rounded-xl transition-all hover:border-accent"
                    style={{ background: '#111318', border: '1px solid #1e2230', color: '#94a3b8' }}>
                    {p}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <Message key={m._id || i} msg={m} onSuggestion={handleSend} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-5 pb-5 pt-2 border-t border-border">
        <div className="flex gap-2 items-end rounded-xl p-3" style={{ background: '#111318', border: '1px solid #1e2230' }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder={activeRepo ? `Ask the ${activeAgent} agent... (Graph RAG powered)` : 'Ingest a repo to start'}
            disabled={!activeRepo || typing}
            rows={1}
            className="flex-1 bg-transparent text-text text-sm outline-none placeholder-muted resize-none font-body leading-relaxed"
            style={{ maxHeight: '120px' }}
          />
          <button
            onClick={() => handleSend()}
            disabled={!activeRepo || !input.trim() || typing}
            className="p-2 rounded-lg transition-all shrink-0"
            style={{
              background: (!activeRepo || !input.trim() || typing) ? 'rgba(255,255,255,0.03)' : 'rgba(0,212,170,0.15)',
              border:     `1px solid ${(!activeRepo || !input.trim() || typing) ? '#1e2230' : 'rgba(0,212,170,0.4)'}`,
              color:      (!activeRepo || !input.trim() || typing) ? '#4b5563' : '#00d4aa',
            }}>
            {typing ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
        <p className="text-xs text-muted mt-1.5 text-center font-mono">
          Enter to send · Graph RAG: intent → cypher → graph → vector → RRF → Groq
        </p>
      </div>
    </div>
  )
}
