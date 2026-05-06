import { useState, type FormEvent } from 'react'

import { useAuth } from '../context/AuthContext'

export function LoginCard() {
  const { login } = useAuth()
  const [email, setEmail] = useState('admin@utoledo.edu')
  const [password, setPassword] = useState('ChangeMe123!')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await login({ email, password })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-card">
      <p className="eyebrow">University of Toledo Athletics</p>
      <h1>Athletic Scholarship Management System</h1>
      <p className="lede">
        Replace the spreadsheet and email chain with one roster workspace, one source-aware import
        flow, and a cleaner handoff into document generation.
      </p>

      <form className="login-form" onSubmit={handleSubmit}>
        <label>
          Email
          <input
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            type="email"
          />
        </label>

        <label>
          Password
          <input
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
          />
        </label>

        {error ? <p className="form-error">{error}</p> : null}

        <button type="submit" className="primary-button" disabled={submitting}>
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>

      <div className="login-note">
        <strong>Demo accounts:</strong> `admin@utoledo.edu`, `football.coach@utoledo.edu`, and
        `softball.coach@utoledo.edu` all use `ChangeMe123!`.
      </div>
    </div>
  )
}
