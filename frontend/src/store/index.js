import { create } from 'zustand'

export const useStore = create((set, get) => ({
  // Repos
  repos: [],
  activeRepo: null,
  setActiveRepo: (repo) => set({ activeRepo: repo }),
  addRepo: (repo) => set((s) => ({ repos: [...s.repos.filter(r => r.repo_id !== repo.repo_id), repo] })),
  setRepos: (repos) => set({ repos }),

  // Graph
  graphData: null,
  setGraphData: (graphData) => set({ graphData }),

  // Chat
  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),

  // UI
  activeAgent: 'explanation',
  setActiveAgent: (a) => set({ activeAgent: a }),
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  loading: false,
  setLoading: (loading) => set({ loading }),

  // Ingestion
  ingestionStatus: null,
  setIngestionStatus: (ingestionStatus) => set({ ingestionStatus }),
}))
