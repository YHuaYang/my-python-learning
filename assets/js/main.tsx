// React 孤岛入口。
//
// 设计目标：Django 模板仍然是页面的主人，React 只接管标注了
// data-react 的元素。模板里写一个 div，这里负责找到它并挂载组件。
//
// 加新组件的三步：
//   1. 在 components/ 下写组件
//   2. 在下面的 registry 里注册名字
//   3. 模板里放 <div data-react="组件名" ...props></div>
import { createRoot } from 'react-dom/client'
import ThemeSelector from '@/components/ThemeSelector'

const THEME_STORAGE_KEY = 'theme'

// 从 <html class="dark"> 读当前主题。
// 初始状态由 base.html <head> 里的内联脚本设置（防闪屏），
// React 只负责读取和后续切换，不参与初始化。
function readCurrentTheme(): string {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function applyTheme(theme: string): void {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
        // 隐私模式下 localStorage 可能抛异常，降级为「仅当前页面生效」
    }
}

// 每个组件工厂：接收 data-* 属性，返回要渲染的元素。
// 之所以用工厂函数而不是直接渲染组件，是因为不同组件需要的 props
// 完全不同，统一在这里做数据转换比让每个组件自己解析 dataset 更清晰。
type IslandFactory = (el: HTMLElement) => React.ReactElement | null

const registry: Record<string, IslandFactory> = {
    'theme-selector': (el) => {
        // 用内联渲染包一层，把主题状态和持久化逻辑收在这里，
        // 组件本身保持纯粹（受控组件），方便测试和复用
        return (
            <ThemeSelector
                value={readCurrentTheme()}
                onChange={applyTheme}
                labels={el.dataset.labels !== 'false'}
            />
        )
    },
}

function mountIslands(): void {
    document.querySelectorAll<HTMLElement>('[data-react]').forEach((el) => {
        const name = el.dataset.react
        if (!name) return

        const factory = registry[name]
        if (!factory) {
            // 模板写了未注册的组件名，开发时提示一下；
            // 线上静默跳过，不能因为一个组件让整页崩掉
            console.warn(`[islands] 未注册的组件: ${name}`)
            return
        }

        const element = factory(el)
        if (!element) return

        // 标记已挂载，避免重复渲染（例如以后做局部重新扫描）
        if (el.dataset.reactMounted === 'true') return
        el.dataset.reactMounted = 'true'

        createRoot(el).render(element)
    })
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountIslands, { once: true })
} else {
    mountIslands()
}
