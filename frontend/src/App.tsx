import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { LoginCard } from './components/LoginCard'
import { useAuth } from './context/AuthContext'
import { AdminDashboardPage } from './pages/AdminDashboardPage'
import { CoachSportPage } from './pages/CoachSportPage'

function AppRoutes() {
  const { user } = useAuth()

  if (!user) {
    return (
      <Routes>
        <Route
          path="*"
          element={
            <div className="centered-shell">
              <LoginCard />
            </div>
          }
        />
      </Routes>
    )
  }

  const defaultCoachSport = user.sports[0]

  return (
    <Routes>
      <Route
        path="/"
        element={
          user.is_admin ? (
            <Navigate to="/admin" replace />
          ) : defaultCoachSport ? (
            <Navigate to={`/sports/${slugifySportName(defaultCoachSport.sport_name)}`} replace />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="/admin" element={<AdminDashboardPage />} />
      <Route path="/sports/:sportSlug" element={<CoachSportPage />} />
      <Route
        path="/login"
        element={
          <Navigate to="/" replace />
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function slugifySportName(value: string) {
  return value.toLowerCase().replaceAll("'", '').replaceAll('&', 'and').replaceAll(' ', '-')
}

function App() {
  const { isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="centered-shell">
        <div className="loading-panel">
          <p className="eyebrow">Loading</p>
          <h1>Checking your session</h1>
        </div>
      </div>
    )
  }

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}

export default App
