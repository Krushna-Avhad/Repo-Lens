import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : '/api'

const api = axios.create({
  baseURL: BASE,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  }
})

export const ingestRepo = async (repoUrl, branch = 'main') => {
  const { data } = await api.post('/ingest', { repo_url: repoUrl, branch })
  return data
}

export const pollStatus = async (jobId) => {
  const { data } = await api.get(`/status/${jobId}`)
  return data
}

export const queryRepo = async (repoId, question, agent = 'explanation') => {
  const { data } = await api.post('/query', { repo_id: repoId, question, agent })
  return data
}

export const getGraph = async (repoId) => {
  const { data } = await api.get(`/graph/${repoId}`)
  return data
}

export const listRepos = async () => {
  const { data } = await api.get('/repos')
  return data
}

export const getRepo = async (repoId) => {
  const { data } = await api.get(`/repo/${repoId}`)
  return data
}
