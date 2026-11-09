"use client";

// GooeyNav：相邻 tab 之间用「粘性颈」连起来的导航。
//
// 移植自 D:\learning\导航样式.txt（原版是 Next.js + shadcn）。
// 三处必须改，否则在本项目跑不起来：
//   1. next/link  → 原生 <a>（Django 渲染页面，不需要客户端路由）
//   2. usePathname → 由 Django 通过 data-path 传进来（React 拿不到 Django 的 url）
//   3. motion/react 的跳转行为不变，但要去掉 next/navigation 依赖
//
// 视觉原理：每两个 tab 之间的缝隙里画一块 SVG，形状是「两头宽、中间收腰」。
// 当前激活 tab 时颈变粗把两块连成一体，视觉上像一团粘液被拉开。
// 收腰程度由 gap 决定，gap 越接近 0 颈越粗。

import {
  useEffect,
  useId,
  useState,
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
} from "react";
import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import { cn } from "@/lib/utils";

// 弹簧参数。
// stiffness 决定「多快向目标靠拢」，值越大越快；
// damping 决定「抑制振荡」，要足够大才不会回弹。
// 迭代记录（ζ = 阻尼比，稳定时间按 2% 包络估算）：
//   200/28 → ζ=0.99，286ms（原版，太快）
//    90/20 → ζ=1.05，422ms
//    60/16 → ζ=1.03，640ms（当前）
// 保持 ζ 略大于 1：不过冲也不拖沙，只是整体变慢。
const SPRING = { type: "spring", stiffness: 60, damping: 16, mass: 1 } as const;

// 缝隙开到这个比例时，颈已经完全断开
const NECK_BREAK = 0.22;

// SVG viewBox 的名义高度；实际会拉伸到 tile 的高度
const NECK_H = 100;

// 颜色过渡时长。跟着弹簧一起放慢到 900ms，
// 否则几何还在动、颜色已经变完了，节奏脱节。
// FADE_OUT 保持 0：退场的 tab 要不带拖影地立即变灰，
// 否则两个 tab 会同时是橙色，看起来像高亮了两个。
const FADE_IN = "transition-colors duration-[900ms] ease-out";
const FADE_OUT = "transition-colors duration-0";

// 未激活 tab 的底色，跟随主题
const BAR = "bg-[#F4F4F9] dark:bg-[#262626]";
// 颈的填充色（用 currentColor + text 控制）
const BAR_TEXT = "text-[#F4F4F9] dark:text-[#262626]";

const SIZES = {
  xs: {
    label: "gap-1 px-2 py-1.5 text-[11px] leading-4 [&_svg]:size-[11px]",
    radius: 8,
    separation: 14,
  },
  sm: {
    label: "gap-1.5 px-3.5 py-2 text-xs leading-4 [&_svg]:size-3",
    radius: 10,
    separation: 16,
  },
  md: {
    label: "gap-2 px-5 py-2.5 text-sm leading-5 [&_svg]:size-3.5",
    radius: 12,
    separation: 20,
  },
  lg: {
    label: "gap-2.5 px-6 py-3 text-base leading-6 [&_svg]:size-4",
    radius: 14,
    separation: 24,
  },
} as const;

export type GooeyNavSize = keyof typeof SIZES;

type NavItem = { label: string; href?: string; icon?: ReactNode };

export type GooeyNavItem = string | NavItem;

const toItem = (item: GooeyNavItem): NavItem =>
  typeof item === "string" ? { label: item } : item;

export type GooeyNavProps = Omit<ComponentProps<"nav">, "onChange"> & {
  items: GooeyNavItem[];
  // 由 Django 传入的当前路径，用于高亮。不是 usePathname
  path?: string;
  value?: number;
  defaultValue?: number;
  onChange?: (index: number) => void;
  size?: GooeyNavSize;
  activeColor?: string;
  activeLabelColor?: string;
  separation?: number;
  radius?: number;
};

// 两条凹曲线在缝隙里相向收窄，围出一块「颈」。
// gap 或 span 非法时返回空字符串，否则会emit 出满是 NaN 的 path
function neckPath(gap: number, span: number) {
  if (!Number.isFinite(gap) || !Number.isFinite(span) || gap <= 0 || span <= 0) {
    return "";
  }
  const waist = NECK_H * (1 - gap / (span * NECK_BREAK));
  if (waist <= 0) return "";
  const start = span - gap;
  const mid = start + gap / 2;
  return `M${start} 0 Q${mid} ${NECK_H - waist} ${span} 0 L${span} ${NECK_H} Q${mid} ${waist} ${start} ${NECK_H} Z`;
}

type SegmentProps = {
  gap: number;
  span: number;
  hasSeam: boolean;
  leftFill: string;
  rightFill: string;
  reduced: boolean;
  radii: Record<string, number>;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
};

function Segment({
  gap,
  span,
  hasSeam,
  leftFill,
  rightFill,
  reduced,
  radii,
  className,
  style,
  children,
}: SegmentProps) {
  const marginLeft = useSpring(gap, SPRING);
  const gradientId = `gooey-neck-${useId().replace(/:/g, "")}`;

  useEffect(() => {
    // reduced 时不走弹簧，直接跳到位
    if (reduced) marginLeft.jump(gap);
    else marginLeft.set(gap);
  }, [gap, marginLeft, reduced]);

  const d = useTransform(marginLeft, (g) => neckPath(g, span));

  return (
    <motion.li
      data-slot="gooey-nav-segment"
      className={cn("relative", className)}
      style={{ ...style, marginLeft }}
      initial={false}
      animate={radii}
      transition={reduced ? { duration: 0 } : SPRING}
    >
      {hasSeam && (
        <svg
          aria-hidden
          width={span}
          viewBox={`0 0 ${span} ${NECK_H}`}
          preserveAspectRatio="none"
          className={cn(
            // right-full 让 SVG 落在外侧缝隙里，挤压到前一块的右边
            "pointer-events-none absolute top-0 right-full h-full",
            BAR_TEXT,
          )}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" x2="1">
              <stop offset="0" stopColor={leftFill} />
              <stop offset="1" stopColor={rightFill} />
            </linearGradient>
          </defs>
          <motion.path d={d} fill={`url(#${gradientId})`} />
        </svg>
      )}
      {children}
    </motion.li>
  );
}

type NavLabelProps = NavItem & {
  isActive: boolean;
  size: GooeyNavSize;
  activeLabelColor: string;
  onSelect: () => void;
};

function NavLabel({
  label,
  href,
  icon,
  isActive,
  size,
  activeLabelColor,
  onSelect,
}: NavLabelProps) {
  const props = {
    "data-slot": "gooey-nav-item",
    "data-active": isActive,
    "aria-current": isActive ? (href ? ("page" as const) : true) : undefined,
    className: cn(
      "flex cursor-pointer items-center whitespace-nowrap font-medium [&_svg]:shrink-0",
      isActive ? FADE_IN : FADE_OUT,
      SIZES[size].label,
      !isActive && "text-[#868593]",
    ),
    style: isActive ? { color: activeLabelColor } : undefined,
    onClick: onSelect,
  } as const;

  // 原版用 next/link，这里是普通 <a>：整页跳转，由 Django 处理路由
  return href ? (
    <a href={href} {...props}>
      {icon}
      {label}
    </a>
  ) : (
    <button type="button" {...props}>
      {icon}
      {label}
    </button>
  );
}

export function GooeyNav({
  items,
  path,
  value,
  defaultValue = 0,
  onChange,
  size = "sm",
  // 用项目的品牌橙，而不是原版的 #FC4C01
  activeColor = "#c25100",
  activeLabelColor = "#ffffff",
  separation,
  radius,
  className,
  ...props
}: GooeyNavProps) {
  const reduced = useReducedMotion() ?? false;

  // 当前路径精确匹配第一项；匹配不到就保持默认高亮。
  // 不做「startsWith」宽松匹配，否则 /projects/ 会同时命中首页
  const routeIndex = items.findIndex((item) => toItem(item).href === path);
  const [uncontrolled, setUncontrolled] = useState(() =>
    routeIndex === -1 ? defaultValue : routeIndex,
  );
  const [seenRoute, setSeenRoute] = useState(routeIndex);

  // 在 render 里改 state 而不是 useEffect：
  // 用 effect 会多一次级联渲染，且首帧高亮是错的
  if (routeIndex !== seenRoute) {
    setSeenRoute(routeIndex);
    if (routeIndex !== -1 && value === undefined) setUncontrolled(routeIndex);
  }

  const active = value ?? uncontrolled;
  const span = separation ?? SIZES[size].separation;
  const corner = radius ?? SIZES[size].radius;

  // 某条缝是否张开。只有挨着激活项的缝才张开，其余闭合
  const open = (seam: number) =>
    seam === 0 ||
    seam === items.length ||
    seam - 1 === active ||
    seam === active;

  const fill = (i: number) => (i === active ? activeColor : "currentColor");

  return (
    <nav
      data-slot="gooey-nav"
      className={cn("inline-block", className)}
      {...props}
    >
      <ul className="flex items-center">
        {items.map((item, i) => {
          const navItem = toItem(item);
          const isActive = i === active;

          return (
            <Segment
              key={`${i}-${navItem.label}`}
              // 闭合的缝收进 1px，避免透出头发丝细线
              gap={i === 0 ? 0 : open(i) ? span : -1}
              span={span}
              hasSeam={i > 0}
              leftFill={fill(i - 1)}
              rightFill={fill(i)}
              reduced={reduced}
              radii={{
                borderTopLeftRadius: open(i) ? corner : 0,
                borderBottomLeftRadius: open(i) ? corner : 0,
                borderTopRightRadius: open(i + 1) ? corner : 0,
                borderBottomRightRadius: open(i + 1) ? corner : 0,
              }}
              className={cn(BAR, isActive ? FADE_IN : FADE_OUT)}
              style={{ backgroundColor: isActive ? activeColor : undefined }}
            >
              <NavLabel
                {...navItem}
                isActive={isActive}
                size={size}
                activeLabelColor={activeLabelColor}
                onSelect={() => {
                  if (value === undefined) setUncontrolled(i);
                  onChange?.(i);
                }}
              />
            </Segment>
          );
        })}
      </ul>
    </nav>
  );
}

export default GooeyNav;
