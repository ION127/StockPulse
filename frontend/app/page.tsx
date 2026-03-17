import { api } from '@/lib/api'
import DashboardClient from './DashboardClient'

export const revalidate = 0

export default async function Page() {
  const [anomalies, sectorTrends] = await Promise.allSettled([
    api.getAnomalies({ days: 7, limit: 100 }),
    api.getSectorTrends(7),
  ])

  return (
    <DashboardClient
      initialAnomalies={anomalies.status === 'fulfilled' ? anomalies.value : []}
      initialSectorTrends={sectorTrends.status === 'fulfilled' ? sectorTrends.value : []}
      lastUpdated={new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
    />
  )
}
