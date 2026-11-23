/**
 * Admin 的 Markdown 编辑器入口。
 *
 * 为什么单独一个入口而不是塞进 main.tsx：
 * Toast UI Editor 约 940KB（压缩前），前台完全用不到它。
 * 塞进 bundle.js 会让每个访客都多下载 1MB。
 * 分成两个入口，只有后台文章编辑页会加载这个文件。
 *
 * 为什么不用 CDN：
 * 项目原则是本地打包（之前选定 Chart 也是同理），
 * 避免依赖外网可用性，也便于离线开发。
 */
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/toastui-editor.css'

// Toast UI 的构造参数里，dark 主题用不同的 CSS 变量。
// 这里只导入了默认（浅色）CSS，暗色通过下面的 CSS 覆盖处理。
import '@toast-ui/editor/dist/theme/toastui-editor-dark.css'

/** Django Admin 的 textarea 通常有这些 id 模式，先按 id 找 */
const TARGET_SELECTOR = 'textarea'

/**
 * 找出需要增强的 textarea。
 *
 * 不能无脑增强所有 textarea：Admin 里搜索框、帮助文本
 * 也可能是 textarea，加上编辑器会破坏布局。
 * 现在只认 data-markdown-editor 属性，由模板显式标注。
 */
function findTargets(): HTMLTextAreaElement[] {
    return Array.from(
        document.querySelectorAll<HTMLTextAreaElement>(
            `${TARGET_SELECTOR}[data-markdown-editor]`,
        ),
    )
}

/**
 * 把一个 textarea 换成 Toast UI 编辑器。
 *
 * 关键：编辑器内容必须同步回原 textarea，否则表单提交时
 * Django 拿到的是空值。Toast UI 提供了 getMarkdown()，
 * 用表单的 submit 事件在提交前写回。
 */
function enhance(textarea: HTMLTextAreaElement): void {
    // 防止重复增强（Admin 有时会重渲染字段）
    if (textarea.dataset.editorReady === 'true') return

    const wrapper = document.createElement('div')
    textarea.parentElement?.insertBefore(wrapper, textarea)

    // 构造要点 try/catch：
    //
    // Toast UI 在解析残缺 Markdown 时会抛 RangeError
    // （实测：未闭合的 ** 或 **** 会让它内部崩掉）。
    // 一旦崩了，编辑器不可用，textarea 又被隐藏，
    // 结果就是「内容看不见也改不了」——比没有编辑器更糟。
    //
    // 所以失败时要把 textarea 原样露出来，保证仍能编辑保存。
    let editor: Editor | null = null
    try {
        editor = new Editor({
            el: wrapper,
            // 初始内容取自 textarea，编辑已有文章时能看到原文
            initialValue: textarea.value,
            initialEditType: 'markdown',
            previewStyle: 'vertical',
            height: '500px',
            language: 'zh-CN',
            usageStatistics: false,
            toolbarItems: [
                ['heading', 'bold', 'italic', 'strike'],
                ['hr', 'quote'],
                ['ul', 'ol', 'task'],
                ['table', 'link', 'image'],
                ['code', 'codeblock'],
            ],
        })
    } catch (err) {
        // 初始化失败：清掉半成品容器，让原 textarea 继续用
        wrapper.remove()
        textarea.style.display = ''
        textarea.dataset.editorFailed = 'true'
        // 不要静默吞掉：这个是数据问题或库 bug，需要能查到
        console.warn('[admin-editor] 编辑器初始化失败，已回退到纯文本框', err)
        return
    }

    // 隐藏原 textarea 而不是删除：Django 的表单校验与
    // 提交都依赖它在表单里存在
    textarea.style.display = 'none'
    textarea.dataset.editorReady = 'true'

    // 把编辑器内容同步回 textarea。
    //
    // 这里有三层兜底，因为这个同步最容易出问题：
    //
    // 1) change 事件：Toast UI 在内容变化时触发。
    //    实测在内部状态异常时（比如 RangeError）可能不触发，
    //    不能单独依赖。
    // 2) submit 事件（capture 阶段）：提交前强制同步。
    //    用 capture 保证跑在 Admin 自己的提交处理之前。
    // 3) 定时轮询：每 500ms 对比一次。
    //    最笨但最可靠——Toast UI 的内部状态异常时，
    //    getMarkdown() 仍能返回正确内容。
    //
    // 写 textarea.value 只是字符串赋值，不触发重排，
    // 500ms 一次的代价可以忽略。
    const sync = () => {
        if (!editor) return
        try {
            const md = editor.getMarkdown()
            if (textarea.value !== md) {
                textarea.value = md
            }
        } catch {
            // getMarkdown 在内部状态异常时会抛错。
            // 这不会丢数据：textarea 里还是上一次成功同步的内容，
            // 而且用户可以点「Markdown」模式切换看原始源码。
        }
    }

    editor.on('change', sync)

    const form = textarea.closest('form')
    if (form) {
        // capture 阶段：保证在 Admin 自己的 submit 处理之前完成同步
        form.addEventListener('submit', sync, { capture: true })
    }

    // 轮询兜底。页面卸载时清理，避免换页后定时器越积越多
    const timer = window.setInterval(sync, 500)
    window.addEventListener('pagehide', () => window.clearInterval(timer), {
        once: true,
    })
}

/**
 * 暗色模式适配。
 *
 * unfold 用 .dark 类切换主题，Toast UI 用自己的一套 CSS 变量。
 * 直接把 unfold 的深色背景铺到编辑器容器上，
 * 否则暗色主题下会是一块白底。
 */
function applyDarkFix(): void {
    if (!document.documentElement.classList.contains('dark')) return
    document.querySelectorAll<HTMLElement>('.toastui-editor-defaultUI').forEach((el) => {
        el.classList.add('toastui-editor-dark')
    })
}

function init(): void {
    const targets = findTargets()
    if (targets.length === 0) return

    targets.forEach(enhance)
    applyDarkFix()
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true })
} else {
    init()
}
