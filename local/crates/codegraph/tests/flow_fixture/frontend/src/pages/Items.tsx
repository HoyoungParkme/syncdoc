/** 화면 */
import { api } from '../api/client'

export function Items({ id }: { id: string }) {
  api.get(`/v1/items/${id}`)
  fetch('/v1/items', { method: 'POST' })
  return <Card id={id} />
}

export function Card({ id }: { id: string }) {
  return <div>{id}</div>
}
