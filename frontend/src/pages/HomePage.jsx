import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, GitBranch, Zap, Network, Shield, ArrowRight, Loader2 } from 'lucide-react'
import { useStore } from '../store'
import { ingestRepo, pollStatus } from '../services/api'
import toast from 'react-hot-toast'

const SAMPLE_REPOS = [
  'https://github.com/tiangolo/fastapi',
  'https://github.com/pallets/flask',
  'https://github.com/django/django',
  'https://github.com/expressjs/express',
]

const FEATURES = [
  { icon: Network, label: 'Living Knowledge Graph', desc: 'NetworkX-powered in-memory code graph built from your repo', color: '#00d4aa' },
  { icon: Zap, label: 'Impact Analysis', desc: 'Predict what breaks before you change a single line', color: '#7c3aed' },
  { icon: Shield, label: 'Refactoring Engine', desc: 'Detect tight coupling, god classes, circular deps', color: '#f59e0b' },
  { icon: GitBranch, label: 'Hybrid Retrieval', desc: 'Graph traversal + vector search for precise answers', color: '#3b82f6' },
]

export default function HomePage() {
  const navigate = useNavigate()
  const { addRepo, setActiveRepo } = useStore()
  const [url, setUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState('')

  const handleIngest = async () => {
    if (!url.trim()) return toast.error('Enter a GitHub repo URL')
    setLoading(true)
    setPhase('Cloning repository...')
    try {
      const { job_id } = await ingestRepo(url.trim(), branch)
      setPhase('Parsing codebase...')

      const poll = async () => {
        const status = await pollStatus(job_id)
        if (status.status === 'ready') {
          addRepo(status)
          setActiveRepo(status)
          toast.success(`${status.name} ingested — ${status.file_count} files, ${status.function_count} functions`)
          navigate('/workspace')
        } else if (status.status === 'error') {
          toast.error(status.error || 'Ingestion failed')
          setLoading(false)
        } else {
          setPhase('Building knowledge graph...')
          setTimeout(poll, 1500)
        }
      }
      setTimeout(poll, 2000)
    } catch (e) {
      toast.error(e.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#0a0b0f' }}>
      {/* Ambient */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full opacity-5"
          style={{ background: 'radial-gradient(circle, #00d4aa 0%, transparent 70%)' }} />
        <div className="absolute top-1/2 left-1/4 w-[400px] h-[400px] rounded-full opacity-3"
          style={{ background: 'radial-gradient(circle, #7c3aed 0%, transparent 70%)' }} />
        {/* Grid lines */}
        <svg className="absolute inset-0 w-full h-full opacity-5" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
              <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#00d4aa" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <nav className="relative z-10 flex items-center justify-between px-8 py-5">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0,212,170,0.1)', border: '1px solid rgba(0,212,170,0.3)' }}>
            <Eye size={16} className="text-accent" />
          </div>
          <span className="font-display text-sm font-medium tracking-widest text-accent">REPO LENS</span>
        </div>
        <span className="text-xs text-muted font-mono border border-border px-3 py-1 rounded-full">v1.0 · Multi-Agent System</span>
      </nav>

      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-16">
        {/* Hero */}
        <div className="text-center max-w-3xl mx-auto mb-14 animate-fade-in">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 text-xs font-mono"
            style={{ background: 'rgba(0,212,170,0.08)', border: '1px solid rgba(0,212,170,0.2)', color: '#00d4aa' }}>
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-slow" />
            Graph RAG · NetworkX · FAISS · LLM Agents
          </div>
          <h1 className="font-display text-5xl md:text-6xl font-medium text-text mb-5 leading-tight">
            Understand Any<br />
            <span style={{ color: '#00d4aa' }}>Codebase</span> Instantly
          </h1>
          <p className="text-text-dim text-lg max-w-xl mx-auto leading-relaxed">
            Repo Lens builds a living knowledge graph of your repository —
            then lets you query, analyze, and improve it with specialized AI agents.
          </p>
        </div>

        {/* Input */}
        <div className="w-full max-w-2xl animate-slide-up" style={{ animationDelay: '0.1s' }}>
          <div className="rounded-xl p-5" style={{ background: '#111318', border: '1px solid #1e2230' }}>
            <div className="flex gap-3 mb-4">
              <input
                type="text"
                value={url}
                onChange={e => setUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleIngest()}
                placeholder="https://github.com/owner/repo"
                className="flex-1 bg-transparent text-text font-mono text-sm outline-none placeholder-muted px-4 py-3 rounded-lg border border-border focus:border-accent transition-colors"
              />
              <input
                type="text"
                value={branch}
                onChange={e => setBranch(e.target.value)}
                placeholder="main"
                className="w-24 bg-transparent text-text font-mono text-sm outline-none placeholder-muted px-3 py-3 rounded-lg border border-border focus:border-accent transition-colors"
              />
            </div>

            <button
              onClick={handleIngest}
              disabled={loading}
              className="w-full py-3.5 rounded-lg font-display text-sm font-medium tracking-wider transition-all flex items-center justify-center gap-2"
              style={{ background: loading ? 'rgba(0,212,170,0.1)' : 'rgba(0,212,170,0.15)', border: '1px solid rgba(0,212,170,0.4)', color: '#00d4aa' }}
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  {phase || 'Processing...'}
                </>
              ) : (
                <>
                  ANALYZE REPOSITORY
                  <ArrowRight size={14} />
                </>
              )}
            </button>

            <div className="flex flex-wrap gap-2 mt-3">
              {SAMPLE_REPOS.map(r => (
                <button key={r} onClick={() => setUrl(r)}
                  className="text-xs font-mono px-2 py-1 rounded text-muted hover:text-accent transition-colors"
                  style={{ background: '#0a0b0f', border: '1px solid #1e2230' }}>
                  {r.split('/').slice(-1)[0]}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto mt-16 w-full">
          {FEATURES.map((f, i) => (
            <div key={f.label} className="p-4 rounded-xl animate-slide-up"
              style={{ background: '#111318', border: '1px solid #1e2230', animationDelay: `${0.15 + i * 0.05}s` }}>
              <f.icon size={18} style={{ color: f.color }} className="mb-3" />
              <div className="text-xs font-display text-text mb-1">{f.label}</div>
              <div className="text-xs text-muted leading-relaxed">{f.desc}</div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
