import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: false,
})

const allowedMarkdownTags = [
  'p', 'br',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'strong', 'em', 's',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'a', 'hr',
  'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
]

markdown.renderer.rules.table_open = () => '<div class="markdown-table-wrap"><table>'
markdown.renderer.rules.table_close = () => '</table></div>'

const defaultLinkOpen = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, environment, renderer) => {
  const token = tokens[index]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer nofollow')
  return defaultLinkOpen
    ? defaultLinkOpen(tokens, index, options, environment, renderer)
    : renderer.renderToken(tokens, index, options)
}

export function renderAssistantMarkdown(source: string): string {
  const rendered = markdown.render(source)
  return DOMPurify.sanitize(rendered, {
    ALLOWED_TAGS: allowedMarkdownTags,
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel', 'class', 'start'],
  })
}
