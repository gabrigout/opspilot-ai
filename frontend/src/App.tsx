import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Skeleton } from '@/components/states'
import { useAuth } from '@/hooks/useAuth'
import { AppLayout } from '@/layouts/AppLayout'
import { lazy, Suspense } from 'react'
import LoginPage from '@/pages/LoginPage'

// Route-level code splitting keeps the initial bundle small (charts are only loaded with the dashboard).
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const OrdersPage = lazy(() => import('@/pages/OrdersPage'))
const CouriersPage = lazy(() => import('@/pages/CouriersPage'))
const RestaurantsPage = lazy(() => import('@/pages/RestaurantsPage'))
const IncidentsPage = lazy(() => import('@/pages/IncidentsPage'))
const CopilotPage = lazy(() => import('@/pages/CopilotPage'))
const ReportsPage = lazy(() => import('@/pages/ReportsPage'))
const ActivityPage = lazy(() => import('@/pages/ActivityPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8"><Skeleton className="h-8 w-48" /></div>
  return user ? <AppLayout /> : <Navigate to="/login" replace />
}

function Page({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<div className="space-y-3" role="status" aria-label="Carregando"><Skeleton className="h-8 w-56" /><Skeleton className="h-64 w-full" /></div>}>{children}</Suspense>
}

function PublicOnly() {
  const { user } = useAuth()
  return user ? <Navigate to="/" replace /> : <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicOnly />}><Route path="/login" element={<LoginPage />} /></Route>
      <Route element={<Protected />}>
        <Route index element={<Page><DashboardPage /></Page>} />
        <Route path="pedidos" element={<Page><OrdersPage /></Page>} />
        <Route path="entregadores" element={<Page><CouriersPage /></Page>} />
        <Route path="restaurantes" element={<Page><RestaurantsPage /></Page>} />
        <Route path="ocorrencias" element={<Page><IncidentsPage /></Page>} />
        <Route path="copilot" element={<Page><CopilotPage /></Page>} />
        <Route path="relatorios" element={<Page><ReportsPage /></Page>} />
        <Route path="atividades" element={<Page><ActivityPage /></Page>} />
        <Route path="configuracoes" element={<Page><SettingsPage /></Page>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
