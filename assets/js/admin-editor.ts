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

// 中文语言包。
//
// 关键：只写 `language: 'zh-CN'` 不够，必须把这个文件导入。
// 它的作用是执行 Editor.setLanguage('zh-CN', {...})，
// 没导入时构造参数里的 'zh-CN' 找不到对应字典，
// 全部回退到英文（按钮 aria-label 与悬停提示都是 Bold/Italic/Headings）。
import '@toast-ui/editor/dist/i18n/zh-cn'

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

    // 禁止在预览区选中文字。
    //
    // 实测问题：预览区（右侧）虽然不可编辑，但文字能被选中。
    // 在那里选中文字再点工具栏，会在源码开头产生孤立的 ****。
    // 预览区本来就只是看的，禁掉选区最直接。
    disablePreviewSelection(wrapper)

    // 拦截「无有效选区」时的行内格式按钮。
    //
    // 真正的原因（比预览区的问题更根本）：
    // Toast UI 的加粗/斜体/删除线/行内代码是「切换」语义。
    // 光标在开头没有选区时点加粗，它会插一对 ** 并等你
    // 在中间打字；但如果你接着保存/切模式，就留下孤立的 ****。
    // 而孤立的 ** 会让下次渲染抛 RangeError，把编辑器搞崩。
    //
    // 所以：源码区没有选区时，直接拦掉这几个按钮，
    // 避免产生会撑死编辑器的脏数据。
    guardInlineFormatting(wrapper)
}

/**
 * 无选区时屏蔽行内格式按钮。
 *
 * 这几个按钮的语义是「把选中的文字包起来」，
 * 没有选区时它们是唯一会留下孤立标记的操作：
 *   bold → **、italic → *、strike → ~~、code → `
 *
 * 标题/列表/表格不需要选区，不屏蔽。
 *
 * 注意：只在 Markdown 模式生效。WYSIWYG 模式下
 * 按钮直接改 DOM，不会产生文本标记。
 */
function guardInlineFormatting(root: HTMLElement): void {
    // 需要选区的按钮的 aria-label（用中文语言包里的文字）
    const needsSelection = new Set([
        '加粗', '斜体字', '删除线', '内嵌代码',
    ])

    const toolbar = root.querySelector<HTMLElement>('.toastui-editor-toolbar')
    if (!toolbar) return

    toolbar.addEventListener(
        'click',
        (event) => {
            const target = (event.target as HTMLElement).closest('button')
            if (!target) return

            const label = target.getAttribute('aria-label') || ''
            if (!needsSelection.has(label)) return

            // WYSIWYG 模式下不拦：那里选中与否都不会产生文本标记
            if (root.classList.contains('toastui-editor-wysiwyg')) return

            // 两个条件都要满足才放行：
            //   1. 有选区（非空）
            //   2. 选区必须在编辑器内部
            //
            // 只查第 1 条不够：实测用 Ctrl+A 或鼠标拖选
            // 把侧边栏、面包屑也选进来时，选区非空但不在编辑器里，
            // Toast UI 同样找不到插入点，照样产生孤立的 ****。
            const sel = window.getSelection()
            const selected = sel?.toString().trim() ?? ''
            // 用 includes 而不是双重否定：
            // `!!(a && b && c)` 读起来要逆着推两遍，
            // 改成布尔表达式直接写可读得多
            const anchorInEditor = sel?.anchorNode != null && root.contains(sel.anchorNode)
            const focusInEditor = sel?.focusNode != null && root.contains(sel.focusNode)

            const valid = selected.length > 0 && anchorInEditor && focusInEditor

            if (!valid) {
                // 阻止按钮自己的 click 处理
                event.preventDefault()
                event.stopPropagation()
                console.error(
                    `[admin-editor] 「${label}」需要先在编辑器内选中文字，`
                    + '否则会在正文里留下孤立标记',
                )
            }
        },
        // capture 阶段：必须比 Toast UI 自己的监听器先执行
        { capture: true },
    )
}

/**
 * 让预览区不可选中。
 *
 * 为什么不在 CSS 里写：
 * 样式表已经很大了，且这个行为只在编辑器初始化后
 * 才能确定目标元素存在，写在 TS 里更直接。
 *
 * user-select 要同时写给标准属性与 -webkit- 前缀：
 * Safari 仍需要前缀才生效。
 */
function disablePreviewSelection(root: HTMLElement): void {
    const preview = root.querySelector<HTMLElement>('.toastui-editor-md-preview')
    if (!preview) return

    preview.style.userSelect = 'none'
    preview.style.setProperty('-webkit-user-select', 'none')

    // 切到 WYSIWYG 模式时，预览区变成编辑区，必须能选中（那是正文）。
    // 所以监听模式切换，按当前模式开关。
    const modeSwitch = root.querySelector<HTMLElement>('.toastui-editor-mode-switch')
    if (!modeSwitch) return

    modeSwitch.addEventListener('click', () => {
        // 点击后等一个事件循环，让 Toast UI 先切完模式
        window.setTimeout(() => {
            const isWysiwyg = root.classList.contains('toastui-editor-wysiwyg')
            const mdPreview = root.querySelector<HTMLElement>('.toastui-editor-md-preview')
            if (!mdPreview) return
            const value = isWysiwyg ? 'auto' : 'none'
            mdPreview.style.userSelect = value
            mdPreview.style.setProperty('-webkit-user-select', value)
        }, 0)
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
