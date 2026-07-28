const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const WS_URL = API_BASE.replace(/^http/, 'ws') + '/ws'

export async function fetchSeats() {
  const res = await fetch(`${API_BASE}/seats`)
  if (!res.ok) throw new Error(`GET /seats returned ${res.status}`)
  return res.json()
}

export async function holdSeat(seatId, userId) {
  const res = await fetch(
    `${API_BASE}/seats/${seatId}/hold?user_id=${encodeURIComponent(userId)}`,
    { method: 'POST' },
  )
  if (res.status === 429) return { rateLimited: true }
  if (!res.ok) throw new Error(`hold returned ${res.status}`)
  return res.json()
}

export async function confirmSeat(seatId, userId, idempotencyKey) {
  // The key is generated once per booking attempt and reused on retry, so a
  // dropped response can never turn into a second booking.
  const params = new URLSearchParams({
    user_id: userId,
    idempotency_key: idempotencyKey,
  })
  const res = await fetch(`${API_BASE}/seats/${seatId}/confirm?${params}`, {
    method: 'POST',
  })
  if (res.status === 429) return { rateLimited: true }
  if (!res.ok) throw new Error(`confirm returned ${res.status}`)
  return res.json()
}
