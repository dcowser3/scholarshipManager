const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

type RequestOptions = {
  method?: 'GET' | 'POST'
  body?: BodyInit | null
  headers?: HeadersInit
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    body: options.body,
    headers: options.headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const payload = await safeJson(response)
    const message =
      payload && typeof payload.detail === 'string'
        ? payload.detail
        : `Request failed with status ${response.status}`
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

async function safeJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    return (await response.json()) as Record<string, unknown>
  } catch {
    return null
  }
}

