import { Routes, Route } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import WorkspacePage from './pages/WorkspacePage'

export default function App() {
  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#111318', color: '#e2e8f0', border: '1px solid #1e2230' },
          success: { iconTheme: { primary: '#00d4aa', secondary: '#0a0b0f' } },
          error: { iconTheme: { primary: '#ef4444', secondary: '#0a0b0f' } },
        }}
      />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/workspace" element={<Layout><WorkspacePage /></Layout>} />
      </Routes>
    </>
  )
}
