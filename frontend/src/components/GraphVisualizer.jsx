import { useEffect, useRef, useState, useCallback } from 'react'
import { useStore } from '../store'
import { getGraph } from '../services/api'
import { Loader2, RefreshCw, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import toast from 'react-hot-toast'

const NODE_COLORS = {
  file:     { bg: '#0d2b1f', border: '#00d4aa', text: '#00d4aa' },
  function: { bg: '#1a1040', border: '#7c3aed', text: '#7c3aed' },
  class:    { bg: '#2b1a08', border: '#f59e0b', text: '#f59e0b' },
  module:   { bg: '#0d1f2b', border: '#3b82f6', text: '#3b82f6' },
  node:     { bg: '#1a1d26', border: '#4b5563', text: '#94a3b8' },
}

export default function GraphVisualizer() {
  const { activeRepo, graphData, setGraphData } = useStore()
  const containerRef = useRef(null)
  const cyRef = useRef(null)
  const [loading, setLoading] = useState(false)
  const [nodeCount, setNodeCount] = useState(0)
  const [edgeCount, setEdgeCount] = useState(0)
  const [selected, setSelected] = useState(null)
  const [cyReady, setCyReady] = useState(false)

  const loadGraph = useCallback(async () => {
    if (!activeRepo) return
    setLoading(true)
    try {
      const data = await getGraph(activeRepo.repo_id)
      setGraphData(data)
      setNodeCount(data.nodes?.length || 0)
      setEdgeCount(data.edges?.length || 0)
    } catch (e) {
      toast.error('Graph load failed: ' + e.message)
    } finally {
      setLoading(false)
    }
  }, [activeRepo, setGraphData])

  useEffect(() => { loadGraph() }, [loadGraph])

  useEffect(() => {
    if (!graphData || !containerRef.current) return
    if (graphData.nodes?.length === 0) return

    // Lazy-load cytoscape
    import('cytoscape').then(({ default: cytoscape }) => {
      if (cyRef.current) { cyRef.current.destroy() }

      const elements = [
        ...graphData.nodes.map(n => ({
          data: {
            id: n.id,
            label: n.label?.slice(0, 24) || n.id.split(':').pop()?.slice(0, 20) || n.id,
            type: n.type || 'node',
            fullLabel: n.label,
            properties: n.properties,
          }
        })),
        ...graphData.edges.map((e, i) => ({
          data: {
            id: `e${i}`,
            source: e.source,
            target: e.target,
            label: e.relationship,
          }
        }))
      ]

      const cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': (el) => NODE_COLORS[el.data('type')]?.bg || NODE_COLORS.node.bg,
              'border-color': (el) => NODE_COLORS[el.data('type')]?.border || NODE_COLORS.node.border,
              'border-width': 1,
              'label': 'data(label)',
              'color': (el) => NODE_COLORS[el.data('type')]?.text || NODE_COLORS.node.text,
              'font-size': '9px',
              'font-family': '"JetBrains Mono", monospace',
              'text-valign': 'center',
              'text-halign': 'center',
              'width': 60,
              'height': 28,
              'shape': 'roundrectangle',
              'text-wrap': 'ellipsis',
              'text-max-width': '52px',
              'padding': '4px',
            }
          },
          {
            selector: 'node:selected',
            style: {
              'border-width': 2,
              'border-color': '#00d4aa',
              'background-color': 'rgba(0,212,170,0.15)',
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 1,
              'line-color': '#1e2230',
              'target-arrow-color': '#2a3040',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'arrow-scale': 0.7,
              'label': 'data(label)',
              'font-size': '7px',
              'color': '#4b5563',
              'font-family': '"JetBrains Mono", monospace',
            }
          },
          {
            selector: 'edge:selected',
            style: { 'line-color': '#00d4aa', 'target-arrow-color': '#00d4aa' }
          },
        ],
        layout: {
          name: 'cose',
          idealEdgeLength: 80,
          nodeRepulsion: 8000,
          gravity: 0.25,
          numIter: 200,
          animate: false,
        },
        userZoomingEnabled: true,
        userPanningEnabled: true,
        boxSelectionEnabled: false,
        minZoom: 0.1,
        maxZoom: 3,
      })

      cy.on('tap', 'node', (e) => {
        const d = e.target.data()
        setSelected({ id: d.id, label: d.fullLabel || d.label, type: d.type, props: d.properties })
      })
      cy.on('tap', (e) => { if (e.target === cy) setSelected(null) })

      cyRef.current = cy
      setCyReady(true)
    }).catch(console.error)

    return () => { if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null } }
  }, [graphData])

  const zoomIn  = () => cyRef.current?.zoom({ level: (cyRef.current.zoom() || 1) * 1.3, renderedPosition: { x: containerRef.current?.offsetWidth / 2, y: containerRef.current?.offsetHeight / 2 } })
  const zoomOut = () => cyRef.current?.zoom({ level: (cyRef.current.zoom() || 1) * 0.7, renderedPosition: { x: containerRef.current?.offsetWidth / 2, y: containerRef.current?.offsetHeight / 2 } })
  const fit     = () => cyRef.current?.fit(undefined, 30)

  return (
    <div className="flex flex-col h-full relative" style={{ background: '#0a0b0f' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
        <div className="flex items-center gap-3 text-xs font-mono text-muted">
          <span><span className="text-accent">{nodeCount}</span> nodes</span>
          <span><span className="text-purple">{edgeCount}</span> edges</span>
          {activeRepo && <span className="text-text-dim">{activeRepo.name}</span>}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={zoomIn}  className="p-1.5 hover:bg-surface rounded transition-colors"><ZoomIn  size={13} className="text-muted" /></button>
          <button onClick={zoomOut} className="p-1.5 hover:bg-surface rounded transition-colors"><ZoomOut size={13} className="text-muted" /></button>
          <button onClick={fit}     className="p-1.5 hover:bg-surface rounded transition-colors"><Maximize2 size={13} className="text-muted" /></button>
          <button onClick={loadGraph} className="p-1.5 hover:bg-surface rounded transition-colors ml-1"><RefreshCw size={13} className="text-muted" /></button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border text-xs font-mono shrink-0">
        {Object.entries(NODE_COLORS).slice(0,4).map(([type, c]) => (
          <span key={type} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ background: c.border }} />
            <span className="text-muted">{type}</span>
          </span>
        ))}
      </div>

      {/* Graph */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 size={16} className="animate-spin text-accent" />
              Building graph...
            </div>
          </div>
        )}
        {!activeRepo && !loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-muted text-sm">Ingest a repository to visualize its graph</p>
          </div>
        )}
        {activeRepo && !loading && nodeCount === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-muted text-sm">No graph data yet — try refreshing</p>
          </div>
        )}
        <div ref={containerRef} className="w-full h-full cy-container" />
      </div>

      {/* Node detail panel */}
      {selected && (
        <div className="absolute bottom-4 right-4 w-56 rounded-xl p-3 animate-slide-up z-20"
          style={{ background: '#111318', border: '1px solid #1e2230' }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-mono" style={{ color: NODE_COLORS[selected.type]?.text || '#94a3b8' }}>
              {selected.type}
            </span>
            <button onClick={() => setSelected(null)} className="text-muted hover:text-text text-xs">✕</button>
          </div>
          <p className="text-xs text-text font-mono break-all mb-1">{selected.label}</p>
          <p className="text-xs text-muted break-all">{selected.id}</p>
          {selected.props?.complexity && (
            <p className="text-xs text-muted mt-1">complexity: <span className="text-amber">{selected.props.complexity}</span></p>
          )}
        </div>
      )}
    </div>
  )
}
