import React from 'react'
import { Card, Statistic } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'

/**
 * StatCard 统计卡片组件
 * @param {string} title - 卡片标题
 * @param {number|string} value - 显示的数值
 * @param {string} prefix - 数值前缀（如 ¥）
 * @param {string} suffix - 数值后缀（如 %）
 * @param {number} change - 环比变化百分比（正数上升，负数下降）
 * @param {string} changeLabel - 变化描述（默认"环比"）
 * @param {React.ReactNode} icon - 左侧图标
 * @param {string} color - 图标/强调色
 */
export default function StatCard({ title, value, prefix, suffix, change, changeLabel = '环比', icon, color }) {
  const isPositive = change > 0
  const isNegative = change < 0

  return (
    <Card
      hoverable
      style={{ height: '100%' }}
      styles={{
        body: { padding: '20px 24px' },
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ color: '#8c8c8c', fontSize: 14, marginBottom: 8 }}>{title}</div>
          <Statistic
            value={value}
            prefix={prefix}
            suffix={suffix}
            valueStyle={{ fontSize: 28, fontWeight: 600 }}
          />
          {change !== undefined && change !== null && (
            <div style={{ marginTop: 8, fontSize: 13 }}>
              <span
                style={{
                  color: isPositive ? '#3f8600' : isNegative ? '#cf1322' : '#8c8c8c',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                {isPositive && <ArrowUpOutlined />}
                {isNegative && <ArrowDownOutlined />}
                <span>{isPositive ? '+' : ''}{typeof change === 'number' ? change.toFixed(1) : change}%</span>
              </span>
              <span style={{ color: '#8c8c8c', marginLeft: 8 }}>{changeLabel}</span>
            </div>
          )}
        </div>
        {icon && (
          <div
            style={{
              fontSize: 36,
              color: color || '#1677ff',
              opacity: 0.8,
              marginLeft: 16,
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </Card>
  )
}
