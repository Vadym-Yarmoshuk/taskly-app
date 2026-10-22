import { Badge, Text } from '../../../design-system'
import type { TodoStats } from '../types'

export function TodoStatsSummary({ stats }: { stats?: TodoStats }) {
  if (!stats) return null
  if (stats.total === 0) return <Text muted>No tasks yet.</Text>
  return (
    <div className="row compact" aria-label="Task summary">
      <Badge variant="info">{stats.active} active</Badge>
      <Badge variant="success">{stats.completed} completed</Badge>
      {stats.overdue > 0 && (
        <Badge variant="warning">{stats.overdue} overdue</Badge>
      )}
    </div>
  )
}
