// React 孤岛入口。
//
// Django 模板仍然是页面的主人，React 只接管标注了 data-react 的元素。
// 加新组件三步：
//   1. 在 components/ 下写组件
//   2. 在下面的 registry 里注册名字
//   3. 模板里放 <div data-react="组件名" ...props></div>
import type { ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import ThemeToggle from '@/components/ThemeToggle'

// 每个组件工厂：接收挂载元素，读取 data-* 属性后返回要渲染的元素。
// 用工厂而不是直接列组件，是因为不同组件的 props 各不相同，
// 统一在这里做 dataset → props 的转换比让组件自己解析更清晰。
type IslandFactory = (el: HTMLElement) => ReactElement | null

const registry: Record<string, IslandFactory> = {
    'theme-toggle': () => <ThemeToggle />,
}

function mountIslands(): void {
    document.querySelectorAll<HTMLElement>('[data-react]').forEach((el) => {
        // 已挂载的跳过，避免以后做局部重新扫描时重复渲染
        if (el.dataset.reactMounted === 'true') return

        const name = el.dataset.react
        if (!name) return

        const factory = registry[name]
        if (!factory) {
            // 模板写了未注册的组件名。开发时提示，线上也提示但不阻塞，
            // 不能因为一个组件让整页交互失效
            console.warn(`[islands] 未注册的组件: ${name}`)
            return
        }

        const element = factory(el)
        if (!element) return

        el.dataset.reactMounted = 'true'
        createRoot(el).render(element)
    })
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountIslands, { once: true })
} else {
    mountIslands()
}
