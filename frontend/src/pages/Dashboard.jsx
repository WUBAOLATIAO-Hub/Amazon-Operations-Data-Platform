import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Row, Col, Select, Card, Spin, message, Segmented } from 'antd'
import {
  DollarOutlined,
  ShoppingCartOutlined,
  PercentageOutlined,
  AccountBookOutlined,
} from '@ant-design/icons'
import * as echarts from 'echarts'
import StatCard from '../components/StatCard'
import { getDashboardSummary, getDashboardTrend, getProductDistribution, getStores, getCountries } from '../api'

// 国家选项
const COUNTRY_OPTIONS = [{ value: '', label: '全部国家' }]

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
  const [month, setMonth] = useState(5)  // 默认5月，与DataQuery保持一致
  const [store, setStore] = useState('')
  const [storeOptions, setStoreOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState(COUNTRY_OPTIONS)

  // 数据状态
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState(null)
  const [trendData, setTrendData] = useState([])
  const [distributionData, setDistributionData] = useState([])
  const [trendMode, setTrendMode] = useState('monthly') // monthly | yearly

  // ECharts 容器
  const chartRef = useRef(null)
  const chartInstanceRef = useRef(null)
  const pieChartRef = useRef(null)
  const pieChartInstanceRef = useRef(null)
  const barChartRef = useRef(null)
  const barChartInstanceRef = useRef(null)

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

  // 加载数据
  useEffect(() => {
    setLoading(true)
    Promise.all([fetchSummary(), fetchTrend(), fetchDistribution()]).finally(() => setLoading(false))
  }, [fetchSummary, fetchTrend, fetchDistribution])

  // 解析 summary 数据
  const summaryData = summary?.current || {}
  const changeData = summary?.change_percent || {}

  // 初始化/更新 ECharts
  useEffect(() => {
    if (!chartRef.current) return

    // 初始化图表实例
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current)
    }
    const chart = chartInstanceRef.current

    // 构建图表数据
    const labels = trendData.map((item) => item.label || item.month || item.period)
    const profitData = trendData.map((item) => item.profit_rmb ?? item.profit ?? 0)
    const salesData = trendData.map((item) => item.sales_rmb ?? item.sales ?? 0)

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function (params) {
          let html = `<strong>${params[0].axisValueLabel}</strong><br/>`
          params.forEach((p) => {
            html += `${p.marker} ${p.seriesName}：¥${formatNumber(p.value)}<br/>`
          })
          return html
        },
      },
      legend: {
        data: ['净利润', '销售额'],
        top: 4,
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 48,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: {
          rotate: labels.length > 12 ? 30 : 0,
        },
      },
      yAxis: {
        type: 'value',
        name: '金额 (RMB)',
        axisLabel: {
          formatter: (val) => {
            if (Math.abs(val) >= 10000) return (val / 10000).toFixed(1) + '万'
            return formatNumber(val)
          },
        },
      },
      series: [
        {
          name: '净利润',
          type: 'line',
          data: profitData,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5 },
          itemStyle: { color: '#52c41a' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(82,196,26,0.25)' },
              { offset: 1, color: 'rgba(82,196,26,0.02)' },
            ]),
          },
        },
        {
          name: '销售额',
          type: 'line',
          data: salesData,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2.5 },
          itemStyle: { color: '#1677ff' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(22,119,255,0.25)' },
              { offset: 1, color: 'rgba(22,119,255,0.02)' },
            ]),
          },
        },
      ],
    }

    chart.setOption(option, true)
  }, [trendData])

  // 初始化/更新饼图
  useEffect(() => {
    if (!pieChartRef.current || distributionData.length === 0) return

    if (!pieChartInstanceRef.current) {
      pieChartInstanceRef.current = echarts.init(pieChartRef.current)
    }
    const chart = pieChartInstanceRef.current

    // 全部店铺+全部国家 → 只显示Top10；选了具体店铺/国家 → 全部显示
    const limit = (!store && !country) ? 10 : distributionData.length
    const pieData = distributionData.slice(0, limit).map(item => ({
      name: item.name,
      value: item.sales_rmb,
    }))

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
        },
        labelLine: { show: false },
        data: pieData,
      }],
    }

    chart.setOption(option, true)
  }, [distributionData, store, country])

  // 初始化/更新柱状图
  useEffect(() => {
    if (!barChartRef.current || distributionData.length === 0) return

    if (!barChartInstanceRef.current) {
      barChartInstanceRef.current = echarts.init(barChartRef.current)
    }
    const chart = barChartInstanceRef.current

    const limit = (!store && !country) ? 10 : distributionData.length
    const chartData = distributionData.slice(0, limit)
    const names = chartData.map(item => item.name)
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
          itemStyle: { color: '#1677ff' },
          barMaxWidth: 40,
        },
        {
          name: '净利润',
          type: 'bar',
          data: profitData,
          itemStyle: {
            color: params => params.value >= 0 ? '#fa8c16' : '#cf1322',
          },
          barMaxWidth: 40,
        },
      ],
    }

    chart.setOption(option, true)
  }, [distributionData, store, country])

  // 监听窗口 resize
  useEffect(() => {
    const handleResize = () => {
      chartInstanceRef.current?.resize()
      pieChartInstanceRef.current?.resize()
      barChartInstanceRef.current?.resize()
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      // cleanup：销毁图表实例
      if (chartInstanceRef.current) {
        chartInstanceRef.current.dispose()
        chartInstanceRef.current = null
      }
      if (pieChartInstanceRef.current) {
        pieChartInstanceRef.current.dispose()
        pieChartInstanceRef.current = null
      }
      if (barChartInstanceRef.current) {
        barChartInstanceRef.current.dispose()
        barChartInstanceRef.current = null
      }
    }
  }, [])

  return (
    <div>
      {/* 筛选栏: 店铺 > 国家 > 年月 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>店铺</span>
        <Select style={{ width: 170 }} value={store} onChange={setStore} options={storeOptions}
          onDropdownVisibleChange={(open) => { if (open) fetchStores() }} />
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>国家</span>
        <Select style={{ width: 130 }} value={country} onChange={setCountry} options={countryOptions} />
        <span style={{ fontWeight: 600, fontSize: 13, color: '#666' }}>时间</span>
        <Select style={{ width: 110 }} value={year} onChange={setYear} options={YEAR_OPTIONS} />
        <Select style={{ width: 90 }} value={month} onChange={setMonth} options={MONTH_OPTIONS} />
        />
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
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

      {/* 饼图和柱状图 */}
      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title="产品销售占比" style={{ marginBottom: 16 }}>
            <div ref={pieChartRef} style={{ width: '100%', height: 400 }} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="产品销售对比 (Top 10)" style={{ marginBottom: 16 }}>
            <div ref={barChartRef} style={{ width: '100%', height: 400 }} />
          </Card>
        </Col>
      </Row>

      {/* 趋势图 */}
      <Card
        title="月度趋势"
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
        <div
          ref={chartRef}
          style={{ width: '100%', height: 400 }}
        />
      </Card>
    </div>
  )
}
