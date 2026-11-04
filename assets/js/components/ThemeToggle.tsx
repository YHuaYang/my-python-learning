import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

const THEME_STORAGE_KEY = 'theme'

/** 从 <html class="dark"> 读当前主题。初始状态由 base.html 内联脚本设置。 */
function readTheme(): 'dark' | 'light' {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function applyTheme(theme: 'dark' | 'light'): void {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
        // 隐私模式下 localStorage 可能抛异常，降级为仅当前页面生效
    }
}

export type ThemeToggleProps = {
    className?: string
}

export function ThemeToggle({ className }: ThemeToggleProps) {
    // 初始值从 DOM 读，与 <head> 内联脚本设置的状态保持一致，
    // 避免 SSR 出来的页面和 React 状态不同步导致的首帧跳变
    const [theme, setTheme] = useState<'dark' | 'light'>(() => readTheme())

    // 监听系统主题变化：用户没手动选过时才跟随。
    // 手动选过（localStorage 有值）就不再被系统设置覆盖
    useEffect(() => {
        const mq = window.matchMedia('(prefers-color-scheme: dark)')
        const onChange = (e: MediaQueryListEvent) => {
            let stored: string | null = null
            try {
                stored = localStorage.getItem(THEME_STORAGE_KEY)
            } catch {
                return
            }
            if (stored !== null) return
            const next = e.matches ? 'dark' : 'light'
            applyTheme(next)
            setTheme(next)
        }
        mq.addEventListener('change', onChange)
        return () => mq.removeEventListener('change', onChange)
    }, [])

    const toggle = () => {
        const next = theme === 'dark' ? 'light' : 'dark'
        applyTheme(next)
        // 必须同步更新 React 状态，否则按钮图标不会变、
        // 且下次点击会因为状态陈旧而算错目标值
        setTheme(next)
    }

    const isDark = theme === 'dark'

    return (
        <button
            type="button"
            onClick={toggle}
            aria-label={isDark ? '切换到亮色模式' : '切换到暗色模式'}
            title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
            aria-pressed={isDark}
            className={cn(
                'inline-flex h-8 w-8 items-center justify-center rounded-lg',
                'text-neutral-500 transition-colors',
                'hover:bg-neutral-100 hover:text-brand',
                'dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-brand',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
                className,
            )}
        >
            {/* 图标显示的是「当前状态」的反面（点击后会发生什么），
                但对读屏器用 aria-label 说明动作 */}
            {isDark ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                    <circle cx="12" cy="12" r="4" />
                    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
            ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
                </svg>
            )}
        </button>
    )
}

export default ThemeToggle
