// 留言板的「写留言」开关。
//
// 为什么只做开关，不接管表单：
//   表单需要 Django 的校验、CSRF token、错误回显。如果 React 渲染表单，
//   要么用 dangerouslySetInnerHTML 塞服务端 HTML（XSS 面 + 类型不安全），
//   要么在客户端重写一遍校验（逻辑两份，必然走偏）。
//   所以表单 HTML 留在 Django 模板里，React 只控制它的显示与隐藏。
//
// 为什么需要 JS 而不是纯 CSS：
//   需要一个「点开后自动聚焦昵称框」的行为，纯 CSS 做不到。

import { useCallback, useState } from 'react'

export type GuestbookToggleProps = {
    // 要控制的表单容器 id
    targetId: string
    // 初始是否展开。提交失败时 Django 会传 true，
    // 否则用户刚填完内容看到表单收起，等于白填
    initialOpen: boolean
}

export function GuestbookToggle({ targetId, initialOpen }: GuestbookToggleProps) {
    const [open, setOpen] = useState(initialOpen)

    const handleOpen = useCallback(() => {
        const el = document.getElementById(targetId)
        if (!el) return
        el.classList.remove('hidden')
        setOpen(true)
        // 展开后聚焦第一个可输入框，省一次点击。
        // 用 requestAnimationFrame 等 class 变化生效再聚焦，
        // 直接 focus 在部分浏览器上对刚显示的隐藏元素无效
        requestAnimationFrame(() => {
            el.querySelector<HTMLInputElement>('input[name="nickname"]')?.focus()
        })
    }, [targetId])

    const handleClose = useCallback(() => {
        document.getElementById(targetId)?.classList.add('hidden')
        setOpen(false)
    }, [targetId])

    return (
        <>
            {!open && (
                <button
                    type="button"
                    onClick={handleOpen}
                    className="rounded bg-brand px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
                >
                    写留言
                </button>
            )}
            {open && (
                <button
                    type="button"
                    onClick={handleClose}
                    className="text-sm text-neutral-500 hover:text-brand dark:text-neutral-400"
                >
                    收起
                </button>
            )}
        </>
    )
}

export default GuestbookToggle
