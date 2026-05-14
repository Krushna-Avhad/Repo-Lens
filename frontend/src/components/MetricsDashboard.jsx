import { useStore } from '../store'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { AlertTriangle, CheckCircle, TrendingUp, Activity } from 'lucide-react'

const PIE_COLORS = ['#00d4aa', '#7c3aed', '#f59e0b', '#3b82f6', '#ef4444']

const RISK_COLOR = (v) => {
  if (v >= 0.7) return '#ef4444'
  if (v >= 0.4) return '#f59e0b'
  return '#00d4aa'
}

const MAINT_COLOR = (v) => {
  if (v >= 0.7) return '#00d4aa'
  if (v >= 0.4) return '#f59e0b'
  return '#ef4444'
}

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="p-4 rounded-xl" style={{ background: '#111318', border: '1px solid #1e2230' }}>
      <div className="flex items-start justify-between mb-3">
        <Icon size={16} style={{ color }} />
        <span className="text-2xl font-display font-medium" style={{ color }}>{value}</span>
      </div>
      <div className="text-xs font-mono text-text mb-0.5">{label}</div>
      <div className="text-xs text-muted">{sub}</div>
    </div>
  )
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="px-3 py-2 rounded-lg text-xs font-mono" style={{ background: '#111318', border: '1px solid #1e2230' }}>
      <p className="text-accent mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || '#94a3b8' }}>{p.name}: {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</p>
      ))}
    </div>
  )
}

export default function MetricsDashboard() {
  const { activeRepo, graphData } = useStore()

  if (!activeRepo) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted text-sm">Ingest a repository to view metrics</p>
      </div>
    )
  }

  const complexity = activeRepo.complexity_score || 0.3
  const coupling   = activeRepo.coupling_score   || 0.2
  const maint      = activeRepo.maintainability_score || 0.8

  // Radar data
  const radarData = [
    { subject: 'Complexity',     A: Math.round(complexity * 100) },
    { subject: 'Coupling',       A: Math.round(coupling   * 100) },
    { subject: 'Maintainability',A: Math.round(maint      * 100) },
    { subject: 'Coverage Risk',  A: Math.round((1 - maint) * 80) },
    { subject: 'Graph Density',  A: Math.min(Math.round(((graphData?.edges?.length || 0) / Math.max(graphData?.nodes?.length || 1, 1)) * 50), 100) },
  ]

  // Node type breakdown
  const nodes = graphData?.nodes || []
  const typeCount = nodes.reduce((acc, n) => {
    acc[n.type] = (acc[n.type] || 0) + 1
    return acc
  }, {})
  const pieData = Object.entries(typeCount).map(([name, value]) => ({ name, value }))

  // Simulated complexity bar data by "module" (top-level path segment)
  const moduleMap = {}
  nodes.forEach(n => {
    const path = n.properties?.path || n.properties?.file || n.label || ''
    const parts = path.split('/')
    const mod = parts.length > 1 ? parts[0] : 'root'
    if (!moduleMap[mod]) moduleMap[mod] = { name: mod, nodes: 0, complexity: 0 }
    moduleMap[mod].nodes++
    moduleMap[mod].complexity += n.properties?.complexity || 1
  })
  const moduleData = Object.values(moduleMap)
    .sort((a, b) => b.complexity - a.complexity)
    .slice(0, 8)
    .map(m => ({ ...m, complexity: +(m.complexity / m.nodes).toFixed(2) }))

  const healthScore = Math.round(maint * 100)
  const healthLabel = healthScore >= 70 ? 'Healthy' : healthScore >= 40 ? 'Needs Attention' : 'Critical'
  const healthIcon  = healthScore >= 70 ? CheckCircle : AlertTriangle
  const HealthIcon  = healthIcon

  return (
    <div className="flex-1 overflow-y-auto p-5" style={{ background: '#0a0b0f' }}>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="font-display text-lg text-text">{activeRepo.name}</h2>
            <p className="text-xs text-muted font-mono mt-0.5">{activeRepo.language} · {activeRepo.url}</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg"
            style={{ background: healthScore >= 70 ? 'rgba(0,212,170,0.08)' : 'rgba(245,158,11,0.08)', border: `1px solid ${healthScore >= 70 ? 'rgba(0,212,170,0.2)' : 'rgba(245,158,11,0.2)'}` }}>
            <HealthIcon size={14} style={{ color: healthScore >= 70 ? '#00d4aa' : '#f59e0b' }} />
            <span className="text-xs font-mono" style={{ color: healthScore >= 70 ? '#00d4aa' : '#f59e0b' }}>
              {healthLabel} · {healthScore}/100
            </span>
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard icon={Activity}    label="Files"     value={activeRepo.file_count}                  sub="parsed & indexed"          color="#00d4aa" />
          <StatCard icon={TrendingUp}  label="Functions" value={activeRepo.function_count}              sub="extracted from AST"        color="#7c3aed" />
          <StatCard icon={Activity}    label="Classes"   value={activeRepo.class_count || 0}            sub="object definitions"        color="#f59e0b" />
          <StatCard icon={AlertTriangle} label="Graph Edges" value={graphData?.edges?.length || 0}    sub="relationships mapped"     color="#3b82f6" />
        </div>

        {/* Score bars */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { label: 'Complexity Score',     value: complexity, color: RISK_COLOR(complexity),  desc: complexity > 0.6 ? 'High cyclomatic complexity detected' : 'Acceptable complexity level' },
            { label: 'Coupling Score',        value: coupling,   color: RISK_COLOR(coupling),    desc: coupling   > 0.6 ? 'Modules are tightly coupled'         : 'Good separation of concerns' },
            { label: 'Maintainability Score', value: maint,      color: MAINT_COLOR(maint),      desc: maint      < 0.4 ? 'Refactoring recommended'              : 'Well-maintained codebase' },
          ].map(s => (
            <div key={s.label} className="p-4 rounded-xl" style={{ background: '#111318', border: '1px solid #1e2230' }}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-mono text-text-dim">{s.label}</span>
                <span className="text-sm font-display font-medium" style={{ color: s.color }}>{Math.round(s.value * 100)}%</span>
              </div>
              <div className="h-1.5 rounded-full mb-3" style={{ background: '#1e2230' }}>
                <div className="h-1.5 rounded-full transition-all" style={{ width: `${s.value * 100}%`, background: s.color }} />
              </div>
              <p className="text-xs text-muted">{s.desc}</p>
            </div>
          ))}
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* Radar */}
          <div className="p-4 rounded-xl col-span-1" style={{ background: '#111318', border: '1px solid #1e2230' }}>
            <p className="text-xs font-mono text-muted uppercase tracking-widest mb-3">Health Radar</p>
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#1e2230" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: '#4b5563', fontSize: 9, fontFamily: 'JetBrains Mono' }} />
                <Radar name="score" dataKey="A" stroke="#00d4aa" fill="#00d4aa" fillOpacity={0.15} strokeWidth={1.5} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          {/* Pie */}
          <div className="p-4 rounded-xl col-span-1" style={{ background: '#111318', border: '1px solid #1e2230' }}>
            <p className="text-xs font-mono text-muted uppercase tracking-widest mb-3">Node Types</p>
            {pieData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" cx="50%" cy="50%" outerRadius={60} strokeWidth={0}>
                      {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip content={<CustomTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-2 mt-2">
                  {pieData.map((d, i) => (
                    <span key={d.name} className="flex items-center gap-1 text-xs font-mono text-muted">
                      <span className="w-2 h-2 rounded-sm" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      {d.name} ({d.value})
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-muted mt-6 text-center">Load graph to see node breakdown</p>
            )}
          </div>

          {/* Module complexity bar */}
          <div className="p-4 rounded-xl col-span-1" style={{ background: '#111318', border: '1px solid #1e2230' }}>
            <p className="text-xs font-mono text-muted uppercase tracking-widest mb-3">Module Complexity</p>
            {moduleData.length > 0 ? (
              <ResponsiveContainer width="100%" height={190}>
                <BarChart data={moduleData} layout="vertical" barSize={10}>
                  <XAxis type="number" tick={{ fill: '#4b5563', fontSize: 8 }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#4b5563', fontSize: 8, fontFamily: 'JetBrains Mono' }} width={60} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="complexity" fill="#7c3aed" radius={[0, 3, 3, 0]}>
                    {moduleData.map((m, i) => (
                      <Cell key={i} fill={m.complexity > 5 ? '#ef4444' : m.complexity > 3 ? '#f59e0b' : '#00d4aa'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-muted mt-6 text-center">Load graph to see module breakdown</p>
            )}
          </div>
        </div>

        {/* Code DNA summary */}
        <div className="p-4 rounded-xl" style={{ background: '#111318', border: '1px solid #1e2230' }}>
          <p className="text-xs font-mono text-muted uppercase tracking-widest mb-4">Code DNA · Fingerprint</p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: 'Language',       value: activeRepo.language?.toUpperCase() || 'N/A',   color: '#00d4aa' },
              { label: 'Graph Nodes',    value: graphData?.nodes?.length || 0,                 color: '#7c3aed' },
              { label: 'Graph Edges',    value: graphData?.edges?.length || 0,                 color: '#3b82f6' },
              { label: 'Avg Complexity', value: (complexity * 10).toFixed(1),                  color: RISK_COLOR(complexity) },
              { label: 'Health Score',   value: `${healthScore}/100`,                          color: MAINT_COLOR(maint) },
            ].map(d => (
              <div key={d.label} className="text-center p-3 rounded-lg" style={{ background: '#0d0f14', border: '1px solid #1e2230' }}>
                <div className="text-lg font-display font-medium mb-1" style={{ color: d.color }}>{d.value}</div>
                <div className="text-xs text-muted font-mono">{d.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
