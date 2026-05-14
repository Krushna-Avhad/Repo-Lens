import { useState } from 'react'
import Sidebar from '../components/Sidebar'
import ChatInterface from '../components/ChatInterface'
import GraphVisualizer from '../components/GraphVisualizer'
import MetricsDashboard from '../components/MetricsDashboard'
import { useStore } from '../store'
import { MessageSquare, Network, BarChart3 } from 'lucide-react'

const TABS = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'graph', label: 'Graph', icon: Network },
  { id: 'metrics', label: 'Metrics', icon: BarChart3 },
]

export default function WorkspacePage() {
  const { sidebarOpen } = useStore()
  const [activeTab, setActiveTab] = useState('chat')
  const [splitView, setSplitView] = useState(true)

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Tab bar */}
        <div className="flex items-center justify-between px-4 border-b border-border shrink-0" style={{ background: '#0d0f14' }}>
          <div className="flex">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className="flex items-center gap-2 px-4 py-3 text-xs font-mono transition-all border-b-2"
                style={{
                  borderColor: activeTab === t.id ? '#00d4aa' : 'transparent',
                  color: activeTab === t.id ? '#00d4aa' : '#4b5563',
                }}
              >
                <t.icon size={13} />
                {t.label.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            onClick={() => setSplitView(v => !v)}
            className="text-xs font-mono px-3 py-1.5 rounded transition-all mr-1"
            style={{
              background: splitView ? 'rgba(0,212,170,0.08)' : 'transparent',
              border: `1px solid ${splitView ? 'rgba(0,212,170,0.2)' : '#1e2230'}`,
              color: splitView ? '#00d4aa' : '#4b5563',
            }}
          >
            SPLIT VIEW
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex">
          {/* Main panel */}
          <div className={`flex flex-col overflow-hidden ${splitView && activeTab !== 'metrics' ? 'w-1/2 border-r border-border' : 'flex-1'}`}>
            {activeTab === 'chat' && <ChatInterface />}
            {activeTab === 'graph' && <GraphVisualizer />}
            {activeTab === 'metrics' && <MetricsDashboard />}
          </div>

          {/* Split panel — always shows graph unless on graph tab */}
          {splitView && activeTab !== 'metrics' && (
            <div className="flex-1 overflow-hidden">
              {activeTab === 'chat' && <GraphVisualizer />}
              {activeTab === 'graph' && <ChatInterface />}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
