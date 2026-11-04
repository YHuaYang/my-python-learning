// 合并 className 的小工具。
//
// 原样板用的是 shadcn/ui 的 cn()，它依赖 clsx + tailwind-merge，
// 能自动消解冲突的 Tailwind 类（如 px-2 与 px-4 同时存在时后者生效）。
// 这里只做最简版：过滤掉假值再拼接。
//
// 为什么不装完整版：项目里组件少，类名冲突靠人工控制即可，
// 不为一个小工具引入两个依赖。若以后组件多了再换成完整实现。

export type ClassValue =
    | string
    | number
    | null
    | undefined
    | false
    | ClassValue[]

export function cn(...inputs: ClassValue[]): string {
    const out: string[] = []

    const walk = (value: ClassValue): void => {
        if (!value) return
        if (Array.isArray(value)) {
            value.forEach(walk)
            return
        }
        out.push(String(value))
    }

    inputs.forEach(walk)
    return out.join(' ')
}
