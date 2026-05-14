import { useStore } from '../store'
import { MessageSquare, Zap, Wrench, Bug, BarChart3, GitBranch, Plus, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const AGENTS = [
  { id: 'explanation', label: 'Explain', icon: MessageSquare, color: '#00d4aa', desc: 'Understand code flow' },
  { id: 'impact', label: 'Impact', icon: Zap, color: '#7c3aed', desc: 'What will break?' },
  { id: 'refactor', label: 'Refactor', icon: Wrench, color: '#f59e0b', desc: 'Detect code smells' },
  { id: 'debug', label: 'Debug', icon: Bug, color: '#ef4444', desc: 'Trace execution path' },
]

const SCORE_COLOR = (v) => v > 0.7 ? '#ef4444' : v > 0.4 ? '#f59e0b' : '#00d4aa'
const MAINT_COLOR = (v) => v > 0.7 ? '#00d4aa' : v > 0.4 ? '#f59e0b' : '#ef4444'

function ScoreBar({ label, value, color }) {
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted">{label}</span>
        <span style={{ color }} className="font-mono">{Math.round(value * 100)}%</span>
      </div>
      <div className="h-1 rounded-full" style={{ background: '#1e2230' }}>
        <div className="h-1 rounded-full transition-all duration-700" style={{ width: `${value * 100}%`, background: color }} />
      </div>
    </div>
  )
}

export default function Sidebar() {
  const { sidebarOpen, activeAgent, setActiveAgent, activeRepo, repos, setActiveRepo, clearMessages } = useStore()
  const navigate = useNavigate()

  if (!sidebarOpen) return null

  return (
    <aside className="w-64 shrink-0 flex flex-col border-r border-border overflow-y-auto" style={{ background: '#0d0f14' }}>
      {/* New repo button */}
      <div className="p-4">
        <button onClick={() => navigate('/')}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-display tracking-wider transition-all"
          style={{ background: 'rgba(0,212,170,0.08)', border: '1px solid rgba(0,212,170,0.2)', color: '#00d4aa' }}>
          <Plus size={13} />
          NEW REPOSITORY
        </button>
      </div>

      {/* Agent selector */}
      <div className="px-4 mb-2">
        <div className="text-xs font-mono text-muted uppercase tracking-widest mb-2">Active Agent</div>
        {AGENTS.map(a => (
          <button key={a.id} onClick={() => { setActiveAgent(a.id); clearMessages() }}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg mb-1 transition-all text-left"
            style={{
              background: activeAgent === a.id ? `rgba(${a.color === '#00d4aa' ? '0,212,170' : a.color === '#7c3aed' ? '124,58,237' : a.color === '#f59e0b' ? '245,158,11' : '239,68,68'},0.12)` : 'transparent',
              border: `1px solid ${activeAgent === a.id ? a.color + '40' : 'transparent'}`,
            }}>
            <a.icon size={14} style={{ color: a.color }} />
            <div>
              <div className="text-xs font-display" style={{ color: activeAgent === a.id ? a.color : '#94a3b8' }}>{a.label}</div>
              <div className="text-xs text-muted leading-tight">{a.desc}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="border-t border-border my-2" />

      {/* Repo list */}
      <div className="px-4 mb-2">
        <div className="text-xs font-mono text-muted uppercase tracking-widest mb-2">Repositories</div>
        {repos.length === 0 && (
          <p className="text-xs text-muted italic">No repos ingested yet</p>
        )}
        {repos.map(r => (
          <button key={r.repo_id} onClick={() => { setActiveRepo(r); clearMessages() }}
            className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg mb-1 transition-all text-left group"
            style={{
              background: activeRepo?.repo_id === r.repo_id ? 'rgba(0,212,170,0.08)' : 'transparent',
              border: `1px solid ${activeRepo?.repo_id === r.repo_id ? 'rgba(0,212,170,0.2)' : 'transparent'}`,
            }}>
            <div>
              <div className="text-xs font-mono text-text truncate max-w-[140px]">{r.name}</div>
              <div className="text-xs text-muted">{r.file_count} files · {r.language}</div>
            </div>
            <ChevronRight size={12} className="text-muted group-hover:text-accent transition-colors" />
          </button>
        ))}
      </div>

      {/* Repo metrics */}
      {activeRepo && (
        <div className="mt-auto border-t border-border p-4">
          <div className="text-xs font-mono text-muted uppercase tracking-widest mb-3">Code DNA</div>
          <ScoreBar label="Complexity" value={activeRepo.complexity_score || 0.3} color={SCORE_COLOR(activeRepo.complexity_score || 0.3)} />
          <ScoreBar label="Coupling" value={activeRepo.coupling_score || 0.2} color={SCORE_COLOR(activeRepo.coupling_score || 0.2)} />
          <ScoreBar label="Maintainability" value={activeRepo.maintainability_score || 0.8} color={MAINT_COLOR(activeRepo.maintainability_score || 0.8)} />
          <div className="mt-3 grid grid-cols-3 gap-2">
            {[
              { label: 'Files', val: activeRepo.file_count },
              { label: 'Functions', val: activeRepo.function_count },
              { label: 'Classes', val: activeRepo.class_count || 0 },
            ].map(s => (
              <div key={s.label} className="text-center p-2 rounded-lg" style={{ background: '#111318', border: '1px solid #1e2230' }}>
                <div className="text-sm font-mono text-accent font-medium">{s.val}</div>
                <div className="text-xs text-muted">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
