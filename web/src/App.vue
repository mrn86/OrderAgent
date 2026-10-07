<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { chatWithAgentStream, decideApproval, getStoredConversationId } from './api/agent'
import { extractHumanCsFromSteps, parseHumanCsPayload } from './utils/humanCs'
import { renderMarkdown } from './utils/markdown'

const input = ref('')
const loading = ref(false)
const error = ref('')
const listRef = ref(null)
const decidingId = ref('')

const messages = ref([
  {
    id: 'welcome',
    role: 'assistant',
    content:
      '你好，我是 Order Agent。可以问我订单、物流、退货退款或发票，例如：帮我查订单号 2026100210000002 的物流。',
  },
])

async function scrollBottom() {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

function applyHumanCs(current, csInfo) {
  if (!current || !csInfo) return
  current.humanCs = csInfo
}

function applyApproval(current, payload) {
  if (!current || (!payload?.requestId && !payload?.conversationId)) return
  current.approval = {
    requestId: payload.requestId || payload.conversationId,
    tool: payload.tool || '',
    args: payload.args || {},
    summary: payload.summary || '',
    status: 'pending',
  }
}

function formatApprovalArgs(args) {
  if (!args || typeof args !== 'object') return ''
  const order = args.order_no || args.order_id || ''
  const amount = args.amount != null ? `${(Number(args.amount) / 100).toFixed(2)} 元` : ''
  const reason = args.reason || ''
  return [order && `订单 ${order}`, amount && `金额 ${amount}`, reason && `原因「${reason}」`]
    .filter(Boolean)
    .join(' · ')
}

async function onApprovalDecide(msg, decision) {
  if (!msg?.approval?.requestId || msg.approval.status !== 'pending' || decidingId.value) return
  decidingId.value = msg.approval.requestId
  error.value = ''
  try {
    const data = await decideApproval(
      msg.approval.requestId,
      decision,
      getStoredConversationId(),
    )
    msg.approval = {
      ...msg.approval,
      status: decision === 'approve' ? 'approved' : 'rejected',
    }
    messages.value.push({
      id: `a-apv-${Date.now()}`,
      role: 'assistant',
      content: data.answer || (decision === 'approve' ? '已批准并执行。' : '已取消。'),
      steps: data.steps || [],
      streaming: false,
      humanCs: null,
    })
  } catch (e) {
    error.value = e?.message || '审批处理失败'
  } finally {
    decidingId.value = ''
    await scrollBottom()
  }
}

async function send() {
  const query = input.value.trim()
  if (!query || loading.value) return

  error.value = ''
  messages.value.push({
    id: `u-${Date.now()}`,
    role: 'user',
    content: query,
  })
  input.value = ''
  loading.value = true
  await scrollBottom()

  const assistantId = `a-${Date.now()}`
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    content: '',
    steps: [],
    streaming: true,
    statusText: '思考中…',
    humanCs: null,
    approval: null,
  })
  await scrollBottom()

  const msg = () => messages.value.find((m) => m.id === assistantId)

  try {
    await chatWithAgentStream(query, async (event) => {
      const current = msg()
      if (!current) return

      if (event.type === 'status') {
        current.statusText = event.content === 'thinking' ? '思考中…' : String(event.content || '')
      } else if (event.type === 'reset_answer') {
        current.content = ''
        current.statusText = '正在查询…'
      } else if (event.type === 'tool_start') {
        const tool = event.tool || ''
        if (tool === 'dispatch_order_expert') current.statusText = '订单专家查询中…'
        else if (tool === 'dispatch_logistics_expert') current.statusText = '物流专家查询中…'
        else if (tool === 'dispatch_invoice_expert') current.statusText = '发票专家查询中…'
        else if (tool === 'escalate_to_human_cs') current.statusText = '准备转人工…'
        else current.statusText = '正在处理…'
        current.steps = [...(current.steps || []), { tool, pending: true }]
      } else if (event.type === 'tool_end') {
        const steps = [...(current.steps || [])]
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          if (steps[i].tool === event.tool && steps[i].pending) {
            const next = { ...steps[i], pending: false }
            if (event.expert) next.expert = event.expert
            if (Array.isArray(event.tools) && event.tools.length) next.tools = event.tools
            steps[i] = next
            break
          }
        }
        current.steps = steps
        if (!current.statusText || current.statusText.startsWith('正在') || current.statusText.includes('查询')) {
          current.statusText = '正在整理答复…'
        }
      } else if (event.type === 'approval_required') {
        applyApproval(current, event)
        current.statusText = '等待人工审批…'
      } else if (event.type === 'human_cs') {
        applyHumanCs(current, {
          needHuman: true,
          reason: event.reason || '当前问题无法自动处理',
          csName: event.csName || '人工客服',
          csUrl: event.csUrl || 'http://www.baidu.com',
          guide: event.guide,
        })
      } else if (event.type === 'token') {
        current.statusText = ''
        current.content = `${current.content || ''}${event.content || ''}`
      } else if (event.type === 'done') {
        current.content = event.answer || current.content || '没有收到有效回复。'
        if (Array.isArray(event.steps) && event.steps.length) {
          current.steps = event.steps
        }
        const csInfo =
          parseHumanCsPayload(event.humanCs) ||
          extractHumanCsFromSteps(current.steps)
        if (csInfo) applyHumanCs(current, csInfo)
        if (event.approvalRequired) {
          applyApproval(current, event.approvalRequired)
        }
        current.streaming = false
        current.statusText = ''
      }

      await scrollBottom()
    })

    const current = msg()
    if (current) {
      current.streaming = false
      current.statusText = ''
      if (!current.content) {
        current.content = '没有收到有效回复。'
      }
      if (!current.humanCs) {
        const csInfo = extractHumanCsFromSteps(current.steps)
        if (csInfo) applyHumanCs(current, csInfo)
      }
    }
  } catch (e) {
    error.value = e?.message || '请求失败'
    const current = msg()
    if (current) {
      current.streaming = false
      current.statusText = ''
      current.isError = true
      current.content = current.content
        ? `${current.content}\n\n调用失败：${error.value}`
        : `调用失败：${error.value}`
    } else {
      messages.value.push({
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `调用失败：${error.value}`,
        isError: true,
      })
    }
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}

const TRACE_LABELS = {
  dispatch_order_expert: '订单专家',
  dispatch_logistics_expert: '物流专家',
  dispatch_invoice_expert: '发票专家',
  escalate_to_human_cs: '转人工',
}

function traceLabel(step) {
  return TRACE_LABELS[step?.tool] || step?.tool || '工具'
}

function fillHint(text) {
  input.value = text
}

onMounted(scrollBottom)
</script>

<template>
  <div class="page">
    <header class="hero">
      <p class="brand">Order Agent</p>
      <h1>订单智能助手</h1>
      <p class="lead">输入问题，点击发送，与 Agent 实时交互。</p>
    </header>

    <main class="chat-shell">
      <section ref="listRef" class="messages" aria-live="polite">
        <article
          v-for="msg in messages"
          :key="msg.id"
          class="row"
          :class="msg.role"
        >
          <div
            class="bubble"
            :class="{ error: msg.isError }"
          >
            <div class="role">{{ msg.role === 'user' ? '你' : 'Agent' }}</div>
            <div v-if="msg.statusText" class="status">{{ msg.statusText }}</div>
            <div
              v-if="msg.role === 'assistant'"
              class="content markdown-body"
              :class="{ streaming: msg.streaming }"
              v-html="renderMarkdown(msg.content || (msg.streaming ? '' : ''))"
            />
            <div v-else class="content plain">{{ msg.content }}</div>
            <span v-if="msg.streaming && msg.content" class="cursor" aria-hidden="true" />
            <details v-if="msg.role === 'assistant' && msg.steps?.length" class="steps">
              <summary>调用路径</summary>
              <ol>
                <li v-for="(step, index) in msg.steps" :key="`${msg.id}-step-${index}`">
                  {{ traceLabel(step) }}
                  <ol v-if="step.tools?.length">
                    <li v-for="(tool, toolIndex) in step.tools" :key="`${msg.id}-tool-${index}-${toolIndex}`">
                      <code>{{ tool }}</code>
                    </li>
                  </ol>
                </li>
              </ol>
            </details>
            <div v-if="msg.approval" class="approval-card">
              <p class="approval-title">高风险操作待审批</p>
              <p class="approval-summary">{{ msg.approval.summary || formatApprovalArgs(msg.approval.args) }}</p>
              <p v-if="msg.approval.tool" class="approval-meta">工具：{{ msg.approval.tool }}</p>
              <div v-if="msg.approval.status === 'pending'" class="approval-actions">
                <button
                  type="button"
                  class="approval-btn approve"
                  :disabled="!!decidingId"
                  @click="onApprovalDecide(msg, 'approve')"
                >
                  {{ decidingId === msg.approval.requestId ? '处理中…' : '批准' }}
                </button>
                <button
                  type="button"
                  class="approval-btn reject"
                  :disabled="!!decidingId"
                  @click="onApprovalDecide(msg, 'reject')"
                >
                  拒绝
                </button>
              </div>
              <p v-else class="approval-status">
                {{ msg.approval.status === 'approved' ? '已批准' : '已拒绝' }}
              </p>
            </div>
            <div v-if="msg.humanCs?.csUrl" class="cs-card">
              <p>该问题暂无法自动处理，建议转人工客服。</p>
              <a
                class="cs-btn"
                :href="msg.humanCs.csUrl"
                target="_blank"
                rel="noopener noreferrer"
              >
                前往{{ msg.humanCs.csName || '人工客服' }}
              </a>
            </div>
          </div>
        </article>
      </section>

      <div class="hints">
        <button type="button" @click="fillHint('帮我查订单号 2026100210000002 的物流到哪了')">
          查物流
        </button>
        <button type="button" @click="fillHint('订单 O20261002002 的退货退款进度怎么样')">
          查售后
        </button>
        <button type="button" @click="fillHint('查看发票 INV20260929001 并给我下载链接')">
          查发票
        </button>
      </div>

      <div v-if="error" class="error-banner" role="alert">
        <p>{{ error }}</p>
        <button type="button" class="error-dismiss" aria-label="关闭错误提示" @click="error = ''">
          关闭
        </button>
      </div>

      <form class="composer" @submit.prevent="send">
        <textarea
          v-model="input"
          rows="2"
          maxlength="500"
          placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
          :disabled="loading"
          @keydown="onKeydown"
        />
        <button class="send" type="submit" :disabled="loading || !input.trim()">
          {{ loading ? '发送中' : '发送' }}
        </button>
      </form>
    </main>
  </div>
</template>

<style scoped>
.page {
  width: min(920px, calc(100% - 32px));
  margin: 0 auto;
  padding: 40px 0 28px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.hero {
  animation: rise 520ms ease both;
}

.brand {
  margin: 0;
  font-family: 'Fraunces', serif;
  font-size: clamp(2.4rem, 6vw, 3.6rem);
  line-height: 1;
  letter-spacing: -0.03em;
  color: var(--ink);
}

.hero h1 {
  margin: 10px 0 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--ink-soft);
}

.lead {
  margin: 8px 0 0;
  color: var(--ink-soft);
  opacity: 0.85;
}

.chat-shell {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 6px);
  box-shadow: var(--shadow);
  backdrop-filter: blur(10px);
  padding: 16px;
  min-height: 62vh;
  animation: rise 700ms ease both;
}

.messages {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px 8px;
}

.row {
  display: flex;
}

.row.user {
  justify-content: flex-end;
}

.row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: min(720px, 92%);
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid var(--line);
  background: var(--bot-bubble);
  word-break: break-word;
  animation: fade-in 280ms ease both;
}

.row.user .bubble {
  background: var(--user-bubble);
  color: #f4faf7;
  border-color: transparent;
}

.bubble.error {
  border-color: rgba(180, 35, 24, 0.35);
  background: #fff5f4;
  color: var(--danger);
}

.error-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(180, 35, 24, 0.28);
  background: #fff5f4;
  color: var(--danger);
  animation: fade-in 220ms ease both;
}

.error-banner p {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.45;
  flex: 1;
}

.error-dismiss {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  opacity: 0.75;
  padding: 0;
}

.error-dismiss:hover {
  opacity: 1;
  text-decoration: underline;
}

.role {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 6px;
}

.content {
  line-height: 1.55;
}

.content.plain {
  white-space: pre-wrap;
}

.steps {
  margin-top: 10px;
  font-size: 12px;
  opacity: 0.9;
}

.steps summary {
  cursor: pointer;
  color: var(--ink-soft);
}

.steps ol {
  margin: 8px 0 0;
  padding-left: 18px;
}

.steps ol ol {
  margin-top: 4px;
}

.steps code {
  display: block;
  margin-top: 2px;
  color: var(--ink-soft);
  word-break: break-all;
}

.status {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--ink-soft);
  font-style: italic;
  animation: status-pulse 1.8s ease-in-out infinite;
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .status {
    animation: none;
  }
}

.approval-card {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(16, 35, 31, 0.16);
  background: rgba(16, 35, 31, 0.04);
}

.approval-title {
  margin: 0;
  font-weight: 700;
  color: var(--ink);
  font-size: 14px;
}

.approval-summary,
.approval-meta,
.approval-status {
  margin: 6px 0 0;
  color: var(--ink-soft);
  font-size: 13px;
}

.approval-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.approval-btn {
  border: none;
  border-radius: 10px;
  padding: 8px 14px;
  font-weight: 700;
  cursor: pointer;
}

.approval-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.approval-btn.approve {
  background: linear-gradient(180deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
}

.approval-btn.reject {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--ink-soft);
}

.cs-card {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(196, 92, 38, 0.28);
  background: rgba(196, 92, 38, 0.08);
}

.cs-card p {
  margin: 0 0 10px;
  color: var(--ink-soft);
  font-size: 14px;
}

.cs-btn {
  display: inline-block;
  border: none;
  border-radius: 10px;
  padding: 8px 14px;
  font-weight: 700;
  cursor: pointer;
  text-decoration: none;
  background: linear-gradient(180deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
}

.cs-btn:hover {
  color: #fff;
  filter: brightness(1.05);
}

.cursor {
  display: inline-block;
  width: 0.55em;
  height: 1.1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--accent);
  animation: blink 1s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.hints {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hints button {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-soft);
  border-radius: 999px;
  padding: 6px 12px;
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease;
}

.hints button:hover {
  transform: translateY(-1px);
  border-color: rgba(196, 92, 38, 0.45);
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: end;
}

textarea {
  width: 100%;
  resize: vertical;
  min-height: 64px;
  max-height: 160px;
  border-radius: 14px;
  border: 1px solid var(--line);
  padding: 12px 14px;
  background: #fff;
  color: var(--ink);
  outline: none;
}

textarea:focus {
  border-color: rgba(196, 92, 38, 0.55);
  box-shadow: 0 0 0 3px rgba(196, 92, 38, 0.12);
}

.send {
  height: 48px;
  min-width: 96px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(180deg, var(--accent) 0%, var(--accent-deep) 100%);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
  transition: transform 160ms ease, opacity 160ms ease;
}

.send:hover:not(:disabled) {
  transform: translateY(-1px);
}

.send:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

@media (max-width: 640px) {
  .page {
    width: min(100% - 16px, 920px);
    padding-top: 24px;
  }

  .composer {
    grid-template-columns: 1fr;
  }

  .send {
    width: 100%;
  }
}
</style>
