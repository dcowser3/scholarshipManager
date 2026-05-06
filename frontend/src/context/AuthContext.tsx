import {
  createContext,
  type PropsWithChildren,
  useContext,
  useEffect,
  useState,
} from 'react'

import { apiRequest } from '../api/client'
import type { AuthUser } from '../types/api'

type LoginInput = {
  email: string
  password: string
}

type AuthContextValue = {
  user: AuthUser | null
  isLoading: boolean
  login: (input: LoginInput) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  async function refresh() {
    try {
      const me = await apiRequest<AuthUser>('/auth/me')
      setUser(me)
    } catch {
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  async function login(input: LoginInput) {
    const nextUser = await apiRequest<AuthUser>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    setUser(nextUser)
  }

  async function logout() {
    await apiRequest('/auth/logout', { method: 'POST' })
    setUser(null)
  }

  useEffect(() => {
    void refresh()
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
