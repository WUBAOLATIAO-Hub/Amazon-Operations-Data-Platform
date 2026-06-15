import React, { useEffect, useRef, useState } from 'react'
import { Card, Statistic } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'

/**
 * 数字滚动动画 Hook
 */
function useAnimatedNumber(target, duration = 1200) {
  const [display, setDisplay] = useState(0)
  const rafRef = useRef(null)
  const startRef = useRef(null)
  const fromRef = useRef(0)

  useEffect(() => {
    const numTarget = typeof target === 'string' ? parseFloat(target) : (target || 0)
    if (isNaN(numTarget)) { setDisplay(0); return }

    const from = fromRef.current
    const diff = numTarget - from
    if (Math.abs(diff) < 0.01) { setDisplay(numTarget); fromRef.current = numTarget; return }

    const startTime = performance.now()
    const animate = (now) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // easeOutExpo
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)
      const current = from + diff * eased
      setDisplay(current)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      } else {
        fromRef.current = numTarget
      }
    }
    rafRef.current = requestAnimationFrame(animate)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [target, duration])

  return display
}

/**
 * StatCard 统计卡片组件
 * @param {string} title - 卡片标题
 * @param {number|string} value - 显示的数值
 * @param {string} prefix - 数值前缀（如 ¥）
 * @param {string} suffix - 数值后缀（如 %）
 * @param {number} change - 环比变化百分比
 * @param {string} changeLabel - 变化描述
 * @param {React.ReactNode} icon - 左侧图标
 * @param {string} color - 图标/强调色
 * @param {boolean} small - 小尺寸模式
 */
export default function StatCard({ title, value, prefix, suffix, change, changeLabel = '环比', icon, color, small }) {
  const isPositive = change > 0
  const isNegative = change < 0

  const numValue = typeof value === 'string' ? parseFloat(value) : (value || 0)
  const animatedValue = useAnimatedNumber(numValue, 1000)

  // 根据数值决定显示精度
  const displayValue = suffix === '%' || suffix === 'x'
    ? animatedValue.toFixed(suffix === 'x' ? 2 : 1)
    : (Number.isInteger(numValue) ? Math.round(animatedValue) : animatedValue.toFixed(2))

  return (
    <Card
      hoverable
      style={{ height: '100%' }}
      styles={{
        body: { padding: small ? '12px 16px' : '20px 24px' },
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: '#8c8c8c', fontSize: small ? 12 : 14, marginBottom: small ? 4 : 8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
          <Statistic
            value={displayValue}
            prefix={prefix}
            suffix={suffix}
            valueStyle={{ fontSize: small ? 20 : 28, fontWeight: 600 }}
          />
          {change !== undefined && change !== null && (
            <div style={{ marginTop: small ? 2 : 8, fontSize: small ? 11 : 13 }}>
              <span
                style={{
                  color: isPositive ? '#3f8600' : isNegative ? '#cf1322' : '#8c8c8c',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 2,
                }}
              >
                {isPositive && <ArrowUpOutlined />}
                {isNegative && <ArrowDownOutlined />}
                <span>{isPositive ? '+' : ''}{typeof change === 'number' ? change.toFixed(1) : change}%</span>
              </span>
              <span style={{ color: '#8c8c8c', marginLeft: 6 }}>{changeLabel}</span>
            </div>
          )}
        </div>
        {icon && (
          <div
            style={{
              fontSize: small ? 24 : 36,
              color: color || '#1677ff',
              opacity: 0.8,
              marginLeft: small ? 8 : 16,
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </Card>
  )
}
