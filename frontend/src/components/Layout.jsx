import { Link } from 'react-router-dom'
import { Eye, PanelLeft } from 'lucide-react'
import { useStore } from '../store'

export default function Layout({ children }) {
  const { toggleSidebar } = useStore()
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <header className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0" style={{ background: '#0d0f14' }}>
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: 'rgba(0,212,170,0.1)', border: '1px solid rgba(0,212,170,0.3)' }}>
            <Eye size={14} className="text-accent" />
          </div>
          <span className="font-display text-sm font-medium tracking-wider text-accent">REPO LENS</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted font-mono">Codebase Intelligence Engine</span>
          <button onClick={toggleSidebar} className="p-1.5 rounded hover:bg-surface transition-colors">
            <PanelLeft size={15} className="text-muted" />
          </button>
        </div>
      </header>
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
