const DEFAULT_CS_URL = import.meta.env.VITE_HUMAN_CS_URL || 'http://www.baidu.com'

export function parseHumanCsPayload(observation) {
  if (!observation) return null

  let data = observation
  if (typeof observation === 'string') {
    try {
      data = JSON.parse(observation)
    } catch {
      return null
    }
  }

  if (!data || typeof data !== 'object') return null
  if (!data.needHuman && !data.csUrl) return null

  return {
    needHuman: Boolean(data.needHuman ?? true),
    reason: data.reason || '当前问题无法自动处理',
    csName: data.csName || '人工客服',
    csUrl: data.csUrl || DEFAULT_CS_URL,
    guide: data.guide || `如需进一步帮助，请联系人工客服：${data.csUrl || DEFAULT_CS_URL}`,
  }
}

export function extractHumanCsFromSteps(steps = []) {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i]
    if (step?.tool !== 'escalate_to_human_cs') continue
    const parsed = parseHumanCsPayload(step.observation)
    if (parsed) return parsed
    return {
      needHuman: true,
      reason: typeof step.input === 'object' ? step.input?.reason : '无法自动处理',
      csName: '人工客服',
      csUrl: DEFAULT_CS_URL,
      guide: `如需进一步帮助，请联系人工客服：${DEFAULT_CS_URL}`,
    }
  }
  return null
}

export function openHumanCs(url = DEFAULT_CS_URL) {
  const target = url || DEFAULT_CS_URL
  const a = document.createElement('a')
  a.href = target
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
