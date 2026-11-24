/**
 * 第三方库的类型声明补充。
 *
 * 为什么需要这个文件：
 * tsconfig 用 moduleResolution: "bundler"，它会严格按
 * package.json 的 exports 字段解析类型。@toast-ui/editor 的
 * exports 里没有声明 types 路径，所以 TypeScript 找不到
 * 它自带的 types/index.d.ts，会报「隐式 any」。
 *
 * 这里手写最小声明，只覆盖我们实际用到的 API。
 * 不引 @toast-ui/editor 的完整类型：那样要绕开 exports
 * 限制，配置更复杂，收益也只有一个编辑器。
 */

declare module '@toast-ui/editor' {
    export interface EditorOptions {
        el: HTMLElement
        initialValue?: string
        initialEditType?: 'markdown' | 'wysiwyg'
        previewStyle?: 'tab' | 'vertical'
        height?: string
        language?: string
        usageStatistics?: boolean
        toolbarItems?: string[][]
    }

    export default class Editor {
        constructor(options: EditorOptions)

        /** 取当前内容的 Markdown 源码 */
        getMarkdown(): string

        /** 取渲染后的 HTML，本项目的存储格式是 Markdown，暂未使用 */
        getHTML(): string

        /** 替换内容，切换文章时可用 */
        setMarkdown(markdown: string): void

        /**
         * 监听编辑器事件。常用事件名：
         *   change —— 内容变化（含输入、粘贴、工具栏操作）
         *   focus / blur —— 焦点得失
         */
        on(eventName: 'change' | 'focus' | 'blur', handler: () => void): void

        /** 取消监听，与 on 成对使用 */
        off(eventName: 'change' | 'focus' | 'blur', handler?: () => void): void

        /** 销毁实例，解绑事件 */
        destroy(): void
    }
}

declare module '@toast-ui/editor/dist/toastui-editor.css'
declare module '@toast-ui/editor/dist/theme/toastui-editor-dark.css'
// 语言包是副作用导入：导入即执行 Editor.setLanguage('zh-CN', {...})，
// 不导出任何值，所以只需声明模块存在。
// 不导入它时，构造参数里的 language: 'zh-CN' 找不到字典，
// 界面会全部回退到英文。
declare module '@toast-ui/editor/dist/i18n/zh-cn'
