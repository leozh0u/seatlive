import { useCallback, useEffect, useRef, useState } from 'react'

import './App.css'
import { WS_URL, confirmSeat, fetchSeats, holdSeat } from './api'

// Each browser tab is a different ticket buyer.
const USER_ID = `user_${crypto.randomUUID().slice(0, 8)}`

export default function App() {
  const [seats, setSeats] = useState([])
  const [held, setHeld] = useState({})
  const [status, setStatus] = useState('')
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  const load = useCallback(() => {
    fetchSeats()
      .then(setSeats)
      .catch(() => setStatus('Cannot reach the API. Is the backend running?'))
  }, [])

  useEffect(load, [load])

  useEffect(() => {
    let closed = false
    let retry

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        const update = JSON.parse(event.data)
        setSeats((prev) =>
          prev.map((seat) =>
            seat.seat_id === update.seat_id ? { ...seat, status: update.status } : seat,
          ),
        )
        // Someone else took a seat this tab was holding.
        if (update.user_id !== USER_ID) {
          setHeld((prev) => {
            if (!prev[update.seat_id]) return prev
            const next = { ...prev }
            delete next[update.seat_id]
            return next
          })
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // The server may have restarted; reconnect and resync, since updates
        // published while disconnected were missed.
        if (!closed) retry = setTimeout(() => { connect(); load() }, 1000)
      }
    }

    connect()

    return () => {
      closed = true
      clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [load])

  async function onHold(seatId) {
    const result = await holdSeat(seatId, USER_ID)
    if (result.rateLimited) {
      setStatus('Rate limited. The API allows 10 requests a minute per client.')
      return
    }
    if (result.held) {
      setHeld((prev) => ({ ...prev, [seatId]: crypto.randomUUID() }))
      setStatus(`Seat ${seatId} is yours for 5 minutes. Confirm to book it.`)
    } else {
      setStatus(`Seat ${seatId} went to someone else.`)
    }
  }

  async function onConfirm(seatId) {
    const result = await confirmSeat(seatId, USER_ID, held[seatId])
    if (result.rateLimited) {
      setStatus('Rate limited. The API allows 10 requests a minute per client.')
      return
    }
    if (result.confirmed) {
      setHeld((prev) => {
        const next = { ...prev }
        delete next[seatId]
        return next
      })
      setStatus(`Seat ${seatId} booked.`)
    } else {
      setStatus(`Seat ${seatId} could not be booked. The hold may have expired.`)
      load()
    }
  }

  function seatClass(seat) {
    if (seat.status === 'booked') return 'booked'
    if (held[seat.seat_id]) return 'mine'
    return seat.status === 'available' ? 'available' : 'held'
  }

  function seatLabel(seat) {
    if (seat.status === 'booked') return 'booked'
    if (held[seat.seat_id]) return 'tap to book'
    return seat.status === 'available' ? 'free' : 'held'
  }

  return (
    <div className="page">
      <h1>SeatLive</h1>
      <p className="subtitle">
        Open this page in two tabs and race for the same seat. You are{' '}
        <span className="you">{USER_ID}</span>.
      </p>

      <div className="seats">
        {seats.map((seat) => {
          const mine = Boolean(held[seat.seat_id])
          return (
            <button
              key={seat.seat_id}
              className={`seat ${seatClass(seat)}`}
              disabled={seat.status === 'booked' || (seat.status === 'held' && !mine)}
              onClick={() => (mine ? onConfirm(seat.seat_id) : onHold(seat.seat_id))}
            >
              Seat {seat.seat_id}
              <span className="state">{seatLabel(seat)}</span>
            </button>
          )
        })}
      </div>

      <p className="status">{status}</p>

      <div className="legend">
        <span className="available">available</span>
        <span className="mine">held by you</span>
        <span className="held">held by someone else</span>
        <span className="booked">booked</span>
      </div>

      <p className="connection">
        {connected ? 'Live updates connected' : 'Reconnecting to live updates...'}
      </p>
    </div>
  )
}
