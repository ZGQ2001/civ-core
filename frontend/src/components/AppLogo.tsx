/**
 * AppLogo：筑核 civ-core 品牌标记（行内 SVG）。
 *
 * 设计语义：六边形外壳 = 锚杆螺母头 / 「核」之细胞；中央工字钢 = 结构核心；
 * 铆钉孔 = 检测节点。蓝图蓝渐变，暗色 IDE 下醒目，16px→1024px 均清晰。
 *
 * 唯一来源：TitleBar / SideBar 空状态等处复用本组件。
 * favicon.svg / src-tauri/app-icon.svg 是同一图形的静态副本（浏览器/打包需独立文件）。
 */
import { useId } from 'react';

interface Props {
  /** 像素边长（正方形）。默认 18，贴合 TitleBar logo 槽位。 */
  size?: number;
  className?: string;
}

export function AppLogo({ size = 18, className }: Props) {
  // 同一图形可被多处行内渲染，渐变 id 必须各实例唯一，否则 DOM 内 id 冲突。
  // useId 每实例唯一且 render 纯净；去冒号避免 SVG url(#...) 引用异常。
  const uid = `cc-logo-${useId().replace(/:/g, '')}`;
  const hex = `${uid}-hex`;
  const beam = `${uid}-beam`;
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="筑核 civ-core"
    >
      <defs>
        <linearGradient
          id={hex}
          x1="22"
          y1="14"
          x2="78"
          y2="86"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#3aa0e3" />
          <stop offset="1" stopColor="#0d5c93" />
        </linearGradient>
        <linearGradient
          id={beam}
          x1="50"
          y1="29"
          x2="50"
          y2="71"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#dcebf7" />
        </linearGradient>
      </defs>
      <polygon
        points="32,18 68,18 86,50 68,82 32,82 14,50"
        fill={`url(#${hex})`}
        stroke={`url(#${hex})`}
        strokeWidth="9"
        strokeLinejoin="round"
      />
      <polygon points="32,18 68,18 86,50 14,50" fill="#ffffff" opacity="0.08" />
      <path
        d="M33,30 H67 V39 H56 V61 H67 V70 H33 V61 H44 V39 H33 Z"
        fill={`url(#${beam})`}
      />
      <g fill={`url(#${hex})`}>
        <circle cx="41" cy="34.5" r="2.1" />
        <circle cx="59" cy="34.5" r="2.1" />
        <circle cx="41" cy="65.5" r="2.1" />
        <circle cx="59" cy="65.5" r="2.1" />
      </g>
    </svg>
  );
}
