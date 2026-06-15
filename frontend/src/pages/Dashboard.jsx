import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Row, Col, Select, Card, Spin, message, Segmented, Tooltip } from 'antd'
import {
  DollarOutlined,
  ShoppingCartOutlined,
  PercentageOutlined,
  AccountBookOutlined,
  FireOutlined,
  AimOutlined,
} from '@ant-design/icons'
import * as echarts from 'echarts'
import StatCard from '../components/StatCard'
import { getDashboardSummary, getDashboardTrend, getProductDistribution, getCostBreakdown, getStores, getCountries } from '../api'

// 年份选项（最近5年）
const currentYear = new Date().getFullYear()
const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => ({
  value: currentYear - i,
  label: `${currentYear - i}年`,
}))

// 月份选项
const MONTH_OPTIONS = [
  { value: 0, label: '全年' },
  ...Array.from({ length: 12 }, (_, i) => ({
    value: i + 1,
    label: `${i + 1}月`,
  })),
]

/** 千分位格式化数字 */
function formatNumber(num) {
  if (num === null || num === undefined) return '0'
  return Number(num).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 格式化百分比 */
function formatPercent(num) {
  if (num === null || num === undefined) return '0.0'
  return Number(num).toFixed(1)
}

export default function Dashboard() {
  // 筛选状态
  const [country, setCountry] = useState('')
  const [year, setYear] = useState(currentYear)
  const [month, setMonth] = useState(new Date().getMonth() + 1)  // 默认当前月
  const [store, setStore] = useState('')
  const [storeOptions, setStoreOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState([{ value: '', label: '全部国家' }])

  // 数据状态
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState(null)
  const [trendData, setTrendData] = useState([])
  const [distributionData, setDistributionData] = useState([])
  const [costData, setCostData] = useState(null)
  const [trendMode, setTrendMode] = useState('monthly')

  // ECharts 容器
  const chartRef = useRef(null)
  const chartInstanceRef = useRef(null)
  const pieChartRef = useRef(null)
  const pieChartInstanceRef = useRef(null)
  const barChartRef = useRef(null)
  const barChartInstanceRef = useRef(null)
  const waterfallRef = useRef(null)
  const waterfallInstanceRef = useRef(null)

  // 获取店铺列表
  useEffect(() => {
    fetchStores(false)
    getCountries().then(res => {
      const opts = [{ value: '', label: '全部国家' }, ...(res.data || []).map(c => ({ value: c.code, label: c.name }))]
      setCountryOptions(opts)
    }).catch(() => {})
  }, [])

  const fetchStores = (autoSelect = true) => {
    getStores().then(res => {
      const opts = [{ value: '', label: '全部店铺' }, ...(res.data || []).map(s => ({ value: s.code, label: s.name }))]
      setStoreOptions(opts)
      if (autoSelect && opts.length > 0) setStore(prev => prev || opts[0].value)
    }).catch(() => {})
  }

  // 获取汇总数据
  const fetchSummary = useCallback(async () => {
    try {
      const params = { year }
      if (country) params.country = country
      if (month) params.month = month
      if (store) params.store = store
      const res = await getDashboardSummary(params)
      setSummary(res.data)
    } catch (err) {
      message.error('获取汇总数据失败：' + (err.response?.data?.detail || err.message))
    }
  }, [country, store, year, month])

  // 获取趋势数据
  const fetchTrend = useCallback(async () => {
    try {
      const params = { dimension: trendMode }
      if (country) params.country = country
      if (store) params.store = store
      const res = await getDashboardTrend(params)
      setTrendData(res.data?.data || [])
    } catch (err) {
      message.error('获取趋势数据失败：' + (err.response?.data?.detail || err.message))
    }
  }, [country, store, trendMode])

  // 获取产品分布数据
  const fetchDistribution = useCallback(async () => {
    try {
      const params = { year }
      if (country) params.country = country
      if (month) params.month = month
      if (store) params.store = store
      const res = await getProductDistribution(params)
      setDistributionData(res.data?.data || [])
    } catch (err) {
      console.error('获取产品分布数据失败', err)
    }
  }, [country, store, year, month])

  // 获取费用拆分数据
  const fetchCostBreakdown = useCallback(async () => {
    try {
      const params = { year }
      if (country) params.country = country
      if (month) params.month = month
      if (store) params.store = store
      const res = await getCostBreakdown(params)
      setCostData(res.data)
    } catch (err) {
      console.error('获取费用拆分数据失败', err)
    }
  }, [country, store, year, month])

  // 加载数据
  useEffect(() => {
    setLoading(true)
    Promise.all([fetchSummary(), fetchTrend(), fetchDistribution(), fetchCostBreakdown()])
      .finally(() => setLoading(false))
  }, [fetchSummary, fetchTrend, fetchDistribution, fetchCostBreakdown])

  // 解析 summary 数据
  const summaryData = summary?.current || {}
  const changeData = summary?.change_percent || {}

  // 辅助：确保图表容器有尺寸后 resize
  const resizeChart = (chart) => {
    if (chart) {
      chart.resize()
      requestAnimationFrame(() => chart.resize())
    }
  }

  // ============ 折线图（净利润 + 销售额 + 订单量） ============
  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current)
    }
    const chart = chartInstanceRef.current

    const labels = trendData.map((item) => item.label)
    const profitData = trendData.map((item) => item.net_profit ?? 0)
    const salesData = trendData.map((item) => item.sales ?? 0)
    const ordersData = trendData.map((item) => item.orders ?? 0)

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function (params) {
          let html = `<strong>${params[0].axisValueLabel}</strong><br/>`
          params.forEach((p) => {
            const unit = p.seriesName === '订单量' ? '单' : '¥'
            html += `${p.marker} ${p.seriesName}：${unit}${formatNumber(p.value)}<br/>`
          })
          return html
        },
      },
      legend: {
        data: ['净利润', '销售额', '订单量'],
        top: 4,
        textStyle: { fontSize: 13 },
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: 56, containLabel: true },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { rotate: labels.length > 12 ? 30 : 0 },
      },
      yAxis: [
        {
          type: 'value',
          name: '金额 (RMB)',
          position: 'left',
          axisLabel: {
            formatter: (val) => {
              if (Math.abs(val) >= 10000) return (val / 10000).toFixed(1) + '万'
              return formatNumber(val)
            },
          },
        },
        {
          type: 'value',
          name: '订单量',
          position: 'right',
          splitLine: { show: false },
          axisLabel: { formatter: (val) => val.toLocaleString() },
        },
      ],
      series: [
        {
          name: '净利润',
          type: 'line',
          data: profitData,
          smooth: 0.4,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5 },
          itemStyle: { color: '#52c41a' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(82,196,26,0.3)' },
              { offset: 1, color: 'rgba(82,196,26,0.02)' },
            ]),
          },
          animationDuration: 1500,
          animationEasing: 'cubicOut',
        },
        {
          name: '销售额',
          type: 'line',
          data: salesData,
          smooth: 0.4,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5 },
          itemStyle: { color: '#1677ff' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(22,119,255,0.3)' },
              { offset: 1, color: 'rgba(22,119,255,0.02)' },
            ]),
          },
          animationDuration: 1800,
          animationEasing: 'cubicOut',
        },
        {
          name: '订单量',
          type: 'line',
          yAxisIndex: 1,
          data: ordersData,
          smooth: 0.4,
          symbol: 'diamond',
          symbolSize: 7,
          lineStyle: { width: 2, type: 'dashed' },
          itemStyle: { color: '#faad14' },
          animationDuration: 2000,
          animationEasing: 'cubicOut',
        },
      ],
    }

    chart.setOption(option, true)
    resizeChart(chart)
  }, [trendData])

  // ============ 瀑布图（费用结构） ============
  useEffect(() => {
    if (!waterfallRef.current || !costData) return
    if (!waterfallInstanceRef.current) {
      waterfallInstanceRef.current = echarts.init(waterfallRef.current)
    }
    const chart = waterfallInstanceRef.current

    const { sales, expenses, net_profit, adjustment, diff } = costData

    // 构建瀑布图数据：销售额 → 各项费用 → 调整 → 净利润
    const categories = ['销售额']
    const baseData = [0]
    const expenseData = [sales]

    let running = sales
    for (const e of expenses) {
      categories.push(e.name)
      baseData.push(running - e.value)
      expenseData.push(e.value)
      running -= e.value
    }

    // 调整项（如果有）
    if (adjustment && Math.abs(adjustment) > 1) {
      categories.push('调整')
      if (adjustment > 0) {
        baseData.push(running)
        expenseData.push(adjustment)
      } else {
        baseData.push(running + adjustment)
        expenseData.push(-adjustment)
      }
      running += adjustment
    }

    // 差额（四舍五入误差等，如果有显著值则显示）
    if (diff && Math.abs(diff) > 100) {
      categories.push('差额')
      if (diff > 0) {
        baseData.push(running)
        expenseData.push(diff)
      } else {
        baseData.push(running + diff)
        expenseData.push(-diff)
      }
      running += diff
    }

    // 净利润（直接用数据库值，保证与 KPI 卡片一致）
    categories.push('净利润')
    baseData.push(0)
    expenseData.push(Math.max(net_profit, 0))

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) {
          const real = params.find(p => p.seriesName === '费用')
          if (!real) return ''
          return `<strong>${real.axisValueLabel}</strong><br/>¥${formatNumber(real.value)}`
        },
      },
      grid: { left: '3%', right: '4%', bottom: '3%', top: 40, containLabel: true },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: { rotate: 30, fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        name: '金额 (RMB)',
        axisLabel: {
          formatter: val => {
            if (Math.abs(val) >= 10000) return (val / 10000).toFixed(1) + '万'
            return val.toLocaleString()
          },
        },
      },
      series: [
        {
          name: '底座',
          type: 'bar',
          stack: 'waterfall',
          itemStyle: { borderColor: 'transparent', color: 'transparent' },
          emphasis: { itemStyle: { borderColor: 'transparent', color: 'transparent' } },
          data: baseData,
        },
        {
          name: '费用',
          type: 'bar',
          stack: 'waterfall',
          barMaxWidth: 50,
          data: expenseData.map((val, i) => ({
            value: val,
            itemStyle: {
              color: i === 0
                // 销售额：蓝色
                ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: '#1677ff' },
                    { offset: 1, color: '#4096ff' },
                  ])
                : i === categories.length - 1
                  // 净利润：绿色/红色
                  ? (net_profit >= 0
                      ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                          { offset: 0, color: '#52c41a' },
                          { offset: 1, color: '#95de64' },
                        ])
                      : new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                          { offset: 0, color: '#cf1322' },
                          { offset: 1, color: '#ff4d4f' },
                        ]))
                  // 费用项：橙色
                  : new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                      { offset: 0, color: '#ff7a45' },
                      { offset: 1, color: '#ffa940' },
                    ]),
              borderRadius: [4, 4, 0, 0],
            },
          })),
          label: {
            show: true,
            position: 'top',
            formatter: function (params) {
              if (params.value <= 0) return ''
              if (params.value >= 10000) return (params.value / 10000).toFixed(1) + '万'
              return params.value.toLocaleString()
            },
            fontSize: 11,
            color: '#666',
          },
          animationDelay: (idx) => idx * 150,
          animationDuration: 800,
          animationEasing: 'elasticOut',
        },
      ],
    }

    chart.setOption(option, true)
    resizeChart(chart)
  }, [costData])

  // ============ 饼图 ============
  useEffect(() => {
    if (!pieChartRef.current || distributionData.length === 0) return
    if (!pieChartInstanceRef.current) {
      pieChartInstanceRef.current = echarts.init(pieChartRef.current)
    }
    const chart = pieChartInstanceRef.current

    const pieLimit = (!store && !country) ? 10 : 15
    let pieData = distributionData.slice(0, pieLimit).map(item => ({
      name: item.name && item.name.length > 20 ? item.name.slice(0, 20) + '...' : (item.name || '未知'),
      value: item.sales_rmb,
    }))
    const rest = distributionData.slice(pieLimit).reduce((s, i) => s + (i.sales_rmb || 0), 0)
    if (rest > 0) pieData.push({ name: '其他', value: rest })

    const option = {
      tooltip: {
        trigger: 'item',
        formatter: '{b}: ¥{c} ({d}%)'
      },
      legend: {
        orient: 'vertical',
        right: '5%',
        top: 'center',
        type: 'scroll',
      },
      series: [{
        name: '销售额',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold' },
          scaleSize: 10,
        },
        labelLine: { show: false },
        data: pieData,
        animationType: 'scale',
        animationEasing: 'elasticOut',
        animationDelay: (idx) => idx * 80,
      }],
    }

    chart.setOption(option, true)
    resizeChart(chart)
  }, [distributionData, store, country])

  // ============ 柱状图 ============
  useEffect(() => {
    if (!barChartRef.current || distributionData.length === 0) return
    if (!barChartInstanceRef.current) {
      barChartInstanceRef.current = echarts.init(barChartRef.current)
    }
    const chart = barChartInstanceRef.current

    const barLimit = (!store && !country) ? 10 : 15
    const chartData = distributionData.slice(0, barLimit)
    const names = chartData.map(item => item.name && item.name.length > 15 ? item.name.slice(0, 15) + '...' : (item.name || '未知'))
    const salesData = chartData.map(item => item.sales_rmb)
    const profitData = chartData.map(item => item.net_profit)

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function(params) {
          let html = `<strong>${params[0].axisValueLabel}</strong><br/>`
          params.forEach(p => {
            html += `${p.marker} ${p.seriesName}：¥${Number(p.value).toLocaleString()}<br/>`
          })
          return html
        },
      },
      legend: { data: ['销售额', '净利润'], top: 4 },
      grid: { left: '3%', right: '4%', bottom: '3%', top: 48, containLabel: true },
      xAxis: {
        type: 'category',
        data: names,
        axisLabel: { rotate: 30, fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        name: '金额 (RMB)',
        axisLabel: {
          formatter: val => {
            if (Math.abs(val) >= 10000) return (val / 10000).toFixed(1) + '万'
            return val.toLocaleString()
          },
        },
      },
      series: [
        {
          name: '销售额',
          type: 'bar',
          data: salesData,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#1677ff' },
              { offset: 1, color: '#4096ff' },
            ]),
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 40,
          animationDelay: (idx) => idx * 100,
          animationDuration: 600,
          animationEasing: 'cubicOut',
        },
        {
          name: '净利润',
          type: 'bar',
          data: profitData,
          itemStyle: {
            color: params => params.value >= 0
              ? new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: '#fa8c16' },
                  { offset: 1, color: '#ffa940' },
                ])
              : new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: '#cf1322' },
                  { offset: 1, color: '#ff4d4f' },
                ]),
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 40,
          animationDelay: (idx) => idx * 100 + 50,
          animationDuration: 600,
          animationEasing: 'cubicOut',
        },
      ],
    }

    chart.setOption(option, true)
    resizeChart(chart)
  }, [distributionData, store, country])

  // 监听窗口 resize + cleanup
  useEffect(() => {
    const handleResize = () => {
      chartInstanceRef.current?.resize()
      pieChartInstanceRef.current?.resize()
      barChartInstanceRef.current?.resize()
      waterfallInstanceRef.current?.resize()
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chartInstanceRef.current?.dispose()
      chartInstanceRef.current = null
      pieChartInstanceRef.current?.dispose()
      pieChartInstanceRef.current = null
      barChartInstanceRef.current?.dispose()
      barChartInstanceRef.current = null
      waterfallInstanceRef.current?.dispose()
      waterfallInstanceRef.current = null
    }
  }, [])

  return (
    <Spin spinning={loading}>
      {/* 筛选栏 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>店铺</span>
        <Select style={{ width: 170 }} value={store} onChange={setStore} options={storeOptions}
          onDropdownVisibleChange={(open) => { if (open) fetchStores() }} />
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>国家</span>
        <Select style={{ width: 130 }} value={country} onChange={setCountry} options={countryOptions} />
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>时间</span>
        <Select style={{ width: 110 }} value={year} onChange={setYear} options={YEAR_OPTIONS} />
        <Select style={{ width: 90 }} value={month} onChange={setMonth} options={MONTH_OPTIONS} />
      </div>

      {/* 统计卡片 — 第一行：核心指标 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="净利润 (RMB)"
            value={summaryData.total_net_profit_rmb ?? 0}
            prefix="¥"
            change={changeData.total_net_profit_rmb}
            icon={<AccountBookOutlined />}
            color="#52c41a"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="销售额 (RMB)"
            value={summaryData.total_product_sales_rmb ?? 0}
            prefix="¥"
            change={changeData.total_product_sales_rmb}
            icon={<DollarOutlined />}
            color="#1677ff"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="订单数"
            value={summaryData.total_order_count ?? 0}
            change={changeData.total_order_count}
            icon={<ShoppingCartOutlined />}
            color="#722ed1"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="净利率"
            value={summaryData.avg_net_profit_rate ? (summaryData.avg_net_profit_rate * 100).toFixed(1) : 0}
            suffix="%"
            change={changeData.avg_net_profit_rate ? (changeData.avg_net_profit_rate * 100).toFixed(1) : null}
            icon={<PercentageOutlined />}
            color="#fa8c16"
          />
        </Col>
      </Row>

      {/* 统计卡片 — 第二行：广告指标 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="ACOS"
            value={summaryData.acos ?? 0}
            suffix="%"
            change={changeData.acos}
            icon={<FireOutlined />}
            color="#eb2f96"
            changeLabel="环比"
            small
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="ROAS"
            value={summaryData.roas ?? 0}
            suffix="x"
            change={changeData.roas}
            icon={<AimOutlined />}
            color="#13c2c2"
            changeLabel="环比"
            small
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="广告花费"
            value={summaryData.total_ad_spend_rmb ?? 0}
            prefix="¥"
            icon={<DollarOutlined />}
            color="#f5222d"
            small
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="点击率 CTR"
            value={summaryData.ctr ?? 0}
            suffix="%"
            icon={<PercentageOutlined />}
            color="#722ed1"
            small
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="CPC"
            value={summaryData.cpc ?? 0}
            prefix="$"
            icon={<DollarOutlined />}
            color="#fa541c"
            small
          />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <StatCard
            title="转化率 CVR"
            value={summaryData.cvr ?? 0}
            suffix="%"
            icon={<ShoppingCartOutlined />}
            color="#52c41a"
            small
          />
        </Col>
      </Row>

      {/* 趋势图 */}
      <Card
        title="月度趋势"
        style={{ marginBottom: 16 }}
        extra={
          <Segmented
            options={[
              { label: '月度', value: 'monthly' },
              { label: '年度', value: 'yearly' },
            ]}
            value={trendMode}
            onChange={setTrendMode}
          />
        }
      >
        <div ref={chartRef} style={{ width: '100%', height: 400 }} />
      </Card>

      {/* 费用瀑布图 + 产品饼图 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="费用结构瀑布图" style={{ height: '100%' }}>
            <div ref={waterfallRef} style={{ width: '100%', height: 400 }} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="产品销售占比" style={{ height: '100%' }}>
            <div ref={pieChartRef} style={{ width: '100%', height: 400 }} />
          </Card>
        </Col>
      </Row>

      {/* 产品柱状图 */}
      <Card title="产品销售对比 (Top 10)">
        <div ref={barChartRef} style={{ width: '100%', height: 400 }} />
      </Card>
    </Spin>
  )
}
