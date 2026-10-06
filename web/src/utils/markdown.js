import { marked } from 'marked'
import purify from 'dompurify'

const DOMPurify = purify?.sanitize ? purify : purify?.default || purify

marked.setOptions({
  gfm: true,
  breaks: true,
})

marked.use({
  renderer: {
    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens)
      const titleAttr = title ? ` title="${title}"` : ''
      return `<a href="${href}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`
    },
  },
})

function unwrapFence(text) {
  const raw = String(text).trim()
  const m = raw.match(/^```(?:markdown|md)?\s*\r?\n([\s\S]*?)\r?\n```\s*$/i)
  return m ? m[1] : String(text)
}

export function renderMarkdown(text) {
  if (!text) return ''
  let html = marked.parse(unwrapFence(text), { async: false })
  if (typeof html !== 'string') html = String(html ?? '')
  if (typeof DOMPurify?.sanitize !== 'function') return html
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel'],
  })
}
