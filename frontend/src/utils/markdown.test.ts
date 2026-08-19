import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AssistantMarkdown from '../components/AssistantMarkdown.vue'
import { renderAssistantMarkdown } from './markdown'

describe('assistant Markdown', () => {
  it('renders headings, emphasis, lists, quotes, rules, and tables', () => {
    const html = renderAssistantMarkdown(`
## Recipe

**Bold** and *italic*

- One
- Two

> Keep warm

---

| Food | State |
| --- | --- |
| Tomato | Fresh |
`)

    expect(html).toContain('<h2>Recipe</h2>')
    expect(html).toContain('<strong>Bold</strong>')
    expect(html).toContain('<em>italic</em>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<hr>')
    expect(html).toContain('<div class="markdown-table-wrap"><table>')
    expect(html).toContain('<td>Tomato</td>')
  })

  it('renders code blocks and safe external links', () => {
    const html = renderAssistantMarkdown(`
Use \`low heat\`.

\`\`\`python
print("soup")
\`\`\`

[Recipe](https://example.com/recipe)
`)

    expect(html).toContain('<code>low heat</code>')
    expect(html).toContain('<pre><code class="language-python">')
    expect(html).toContain('href="https://example.com/recipe"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer nofollow"')
  })

  it('does not allow embedded HTML or javascript links', () => {
    const html = renderAssistantMarkdown(
      '<img src=x onerror="alert(1)"> [bad](javascript:alert(1))',
    )

    expect(html).not.toContain('<img')
    expect(html).not.toContain('onerror=')
    expect(html).not.toContain('href="javascript:')
  })

  it('renders incomplete streaming Markdown without crashing', async () => {
    const wrapper = mount(AssistantMarkdown, {
      props: { content: '## Recipe\n\n```js\nconst pan =', streaming: true },
    })

    expect(wrapper.find('h2').text()).toBe('Recipe')
    expect(wrapper.find('pre code').text()).toContain('const pan =')

    await wrapper.setProps({
      content: '## Recipe\n\n```js\nconst pan = "hot"\n```',
      streaming: false,
    })
    expect(wrapper.find('pre code').text()).toContain('const pan = "hot"')
    expect(wrapper.classes()).not.toContain('message-content--streaming')
  })
})
