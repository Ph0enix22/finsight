export const MOCK_MODE = import.meta.env.VITE_MOCK_API === 'true'

const BASE_URL = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
}
