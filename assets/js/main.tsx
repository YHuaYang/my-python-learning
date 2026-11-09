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
import { GooeyNav, type GooeyNavItem } from '@/components/GooeyNav'
import { GuestbookToggle } from '@/components/GuestbookToggle'

// 每个组件工厂：接收挂载元素，读取 data-* 属性后返回要渲染的元素。
type IslandFactory = (el: HTMLElement) => ReactElement | null

/** 从 <script type="application/json"> 读数据。
 *  导航项需要 Django 的 {% url %} 生成 href，JS 里编不出来，
 *  所以由模板渲染成 JSON 再读。 */
function readJsonScript<T>(id: string, fallback: T): T {
    const node = document.getElementById(id)
    if (!node || !node.textContent) return fallback
    try {
        return JSON.parse(node.textContent) as T
    } catch {
        console.warn(`[islands] JSON 解析失败: #${id}`)
        return fallback
    }
}

const registry: Record<string, IslandFactory> = {
    'theme-toggle': () => <ThemeToggle />,

    'gooey-nav': (el) => {
        const items = readJsonScript<GooeyNavItem[]>('nav-items', [])
        if (items.length === 0) return null
        // 当前路径由 Django 的 request.path 传入，用于高亮
        return <GooeyNav items={items} path={el.dataset.path ?? ''} size="sm" />
    },

    'guestbook-toggle': (el) => (
        <GuestbookToggle
            targetId={el.dataset.target ?? ''}
            initialOpen={el.dataset.open === 'true'}
        />
    ),
}

function mountIslands(): void {
    document.querySelectorAll<HTMLElement>('[data-react]').forEach((el) => {
        // 已挂载的跳过，避免以后做局部重新扫描时重复渲染
        if (el.dataset.reactMounted === 'true') return

        const name = el.dataset.react
        if (!name) return

        const factory = registry[name]
        if (!factory) {
            console.warn(`[islands] 未注册的组件: ${name}`)
            return
        }

        const element = factory(el)
        if (!element) {
            // 组件根据数据判断不需要渲染（比如没有歌单）
            return
        }

        el.dataset.reactMounted = 'true'
        createRoot(el).render(element)
    })
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountIslands, { once: true })
} else {
    mountIslands()
}
