const TOKEN = import.meta.env.VITE_ACCESS_TOKEN || 'test-token'
const API_BASE = import.meta.env.VITE_API_BASE || '/v1'
const CONVERSATION_KEY = 'order_agent_conversation_id'

export function getStoredConversationId() {
  try {
    return sessionStorage.getItem(CONVERSATION_KEY) || ''
  } catch {
    return ''
  }
}

export function setStoredConversationId(id) {
  if (!id) return
  try {
    sessionStorage.setItem(CONVERSATION_KEY, id)
  } catch {
    // ignore
  }
}

export class ApiError extends Error {
  constructor(message, { status = 0, retryAfter = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

function parseRetryAfter(response) {
  const raw = response.headers.get('Retry-After')
  if (!raw) return null
  const seconds = Number.parseInt(raw, 10)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

async function readErrorDetail(response) {
  try {
    const body = await response.json()
    const detail = body?.detail ?? body?.message ?? ''
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item === 'string' ? item : item?.msg || JSON.stringify(item)))
        .filter(Boolean)
        .join('；')
    }
    if (detail && typeof detail === 'object') {
      return detail.message || JSON.stringify(detail)
    }
    return typeof detail === 'string' ? detail : ''
  } catch {
    return ''
  }
}

async function ensureOk(response) {
  if (response.ok) return
  const detail = await readErrorDetail(response)
  const retryAfter = parseRetryAfter(response)
  const status = response.status

  if (status === 429) {
    const wait =
      retryAfter != null ? `请约 ${retryAfter} 秒后再试` : '请稍后再试'
    throw new ApiError(
      detail ? `${detail}（${wait}）` : `请求过于频繁，${wait}`,
      { status, retryAfter },
    )
  }
  if (status === 401 || status === 403) {
    throw new ApiError(detail || '鉴权失败，请检查访问令牌', { status, retryAfter })
  }
  if (status >= 500) {
    throw new ApiError(detail || '服务暂时不可用，请稍后重试', { status, retryAfter })
  }
  throw new ApiError(detail || `请求失败（HTTP ${status}）`, { status, retryAfter })
}

export async function chatWithAgent(query, conversationId = getStoredConversationId()) {
  const response = await fetch(`${API_BASE}/agent/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify({
      query,
      ...(conversationId ? { conversationId } : {}),
    }),
  })

  await ensureOk(response)

  const payload = await response.json()
  if (payload.code !== 0) {
    throw new ApiError(payload.message || 'Agent 调用失败', { status: 200 })
  }
  if (payload.data?.conversationId) {
    setStoredConversationId(payload.data.conversationId)
  }
  return payload.data
}

export async function decideApproval(requestId, decision, conversationId = getStoredConversationId()) {
  // HITL: requestId === conversationId（thread_id）
  const rid = requestId || conversationId
  const response = await fetch(
    `${API_BASE}/agent/approvals/${encodeURIComponent(rid)}/decide`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${TOKEN}`,
      },
      body: JSON.stringify({
        decision,
        ...(conversationId ? { conversationId } : {}),
      }),
    },
  )
  await ensureOk(response)
  const payload = await response.json()
  if (payload.code !== 0) {
    throw new ApiError(payload.message || '审批处理失败', { status: 200 })
  }
  if (payload.data?.conversationId) {
    setStoredConversationId(payload.data.conversationId)
  }
  return payload.data
}

async function createStreamSession(query, conversationId) {
  const response = await fetch(`${API_BASE}/agent/chat/stream/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify({
      query,
      ...(conversationId ? { conversationId } : {}),
    }),
  })
  await ensureOk(response)
  const payload = await response.json()
  if (payload.code !== 0 || !payload.data?.sessionId) {
    throw new ApiError(payload.message || '创建流式会话失败', { status: 200 })
  }
  if (payload.data.conversationId) {
    setStoredConversationId(payload.data.conversationId)
  }
  return payload.data
}

function parseSseData(raw) {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * 使用 EventSource 订阅 SSE，断线后由浏览器自动重连（Last-Event-ID 回放）。
 * 历史由后端按 conversationId 维护，前端只传 ID。
 * onEvent 收到: status | tool_start | tool_end | token | human_cs | approval_required | done | error
 */
export async function chatWithAgentStream(query, onEvent) {
  const conversationId = getStoredConversationId()
  const { sessionId, conversationId: cid } = await createStreamSession(query, conversationId)
  if (cid) {
    onEvent?.({ type: 'conversation', conversationId: cid })
  }
  const url = `${API_BASE}/agent/chat/stream?sessionId=${encodeURIComponent(sessionId)}`

  return new Promise((resolve, reject) => {
    const es = new EventSource(url)
    let settled = false

    const finish = (ok, error) => {
      if (settled) return
      settled = true
      es.close()
      if (ok) resolve()
      else reject(error)
    }

    const handlePayload = (raw) => {
      const event = parseSseData(raw)
      if (!event) return
      if (event.conversationId) {
        setStoredConversationId(event.conversationId)
      }
      onEvent?.(event)
      if (event.type === 'done') {
        finish(true)
        return
      }
      if (event.type === 'error') {
        finish(false, new ApiError(event.message || 'Agent 流式调用失败'))
      }
    }

    es.onmessage = (e) => handlePayload(e.data)
    es.addEventListener('complete', (e) => handlePayload(e.data))

    es.onerror = () => {
      // CONNECTING：浏览器正在按 retry 间隔重连，不视为失败
      if (es.readyState === EventSource.CLOSED && !settled) {
        finish(false, new ApiError('SSE 连接已关闭'))
      }
    }
  })
}
