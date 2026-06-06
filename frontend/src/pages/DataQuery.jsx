import React, { useState, useEffect, useRef } from 'react'
import { Select, Input, Button, Table, Card, message, Space, Statistic, Row, Col } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import { getMonthlySummary, getStores } from '../api'

const COUNTRY_OPTIONS = [
  { value: 'US', label: '美国站' },
  { value: 'UK', label: '英国站' },
  { value: 'DE', label: '德国站' },
]

const YEAR_OPTIONS = [
  { value: 0, label: '全部' },
  { value: 2026, label: '2026年' },
  { value: 2025, label: '2025年' },
]

const MONTH_OPTIONS = [
  { value: 0, label: '全部' },
  ...Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` })),
]

function fmtMoney(n) {
  if (n === null || n === undefined) return '-'
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(n) {
  if (n === null || n === undefined) return '-'
  return Number(n).toFixed(1) + '%'
}

export default function DataQuery() {
  const [country, setCountry] = useState('US')
  const [year, setYear] = useState(2026)
  const [month, setMonth] = useState(5)
  const [store, setStore] = useState('')
  const [storeOptions, setStoreOptions] = useState([])
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState([])
  const [pagination, setPagination] = useState({ current: 1, pageSize: 200, total: 0 })
  const [sorter, setSorter] = useState({})

  // 用ref存最新keyword，避免闭包问题
  const keywordRef = useRef(keyword)
  keywordRef.current = keyword

  const fetchData = async (page = 1, pageSize = 200, sortField, sortOrder) => {
    setLoading(true)
    try {
      const kw = keywordRef.current.trim()
      const params = { country, page, page_size: pageSize }
      if (store) params.store = store
      if (year) params.year = year
      if (month) params.month = month
      if (kw) params.keyword = kw
      if (sortField) params.sort_by = sortField
      if (sortOrder) params.sort_order = sortOrder === 'ascend' ? 'asc' : 'desc'

      console.log('查询参数:', params)  // 调试用

      const res = await getMonthlySummary(params)
      const result = res.data
      setData(result.data || [])
      setPagination((prev) => ({ ...prev, current: page, pageSize, total: result.total || 0 }))
    } catch (err) {
      message.error('查询失败：' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])
  const fetchStores = (autoSelect = true) => {
    getStores(country).then(res => {
      const opts = (res.data || []).map(s => ({ value: s.code, label: s.name }))
      setStoreOptions(opts)
      if (autoSelect && opts.length > 0) setStore(prev => prev || opts[0].value)
    }).catch(() => {})
  }

  useEffect(() => { setStore(''); setStoreOptions([]); fetchStores(false) }, [country])

  const handleSearch = () => {
    fetchData(1, pagination.pageSize, sorter.field, sorter.order)
  }

  const handleReset = () => {
    setKeyword('')
    setYear(2026)
    setMonth(5)
    keywordRef.current = ''
    setTimeout(() => fetchData(1, 200), 50)
  }

  const handleTableChange = (pag, _, newSorter) => {
    setSorter(newSorter)
    fetchData(pag.current, pag.pageSize, newSorter.field, newSorter.order)
  }

  // 汇总
  const totals = data.reduce(
    (acc, r) => ({
      order_count: acc.order_count + r.order_count,
      product_sales_usd: acc.product_sales_usd + r.product_sales_usd,
      product_sales_rmb: acc.product_sales_rmb + r.product_sales_rmb,
      commission_usd: acc.commission_usd + r.commission_usd,
      fba_fee_usd: acc.fba_fee_usd + r.fba_fee_usd,
      ad_spend_usd: acc.ad_spend_usd + r.ad_spend_usd,
      storage_fee_usd: acc.storage_fee_usd + r.storage_fee_usd,
      product_cost_rmb: acc.product_cost_rmb + r.product_cost_rmb,
      freight_cost_rmb: acc.freight_cost_rmb + r.freight_cost_rmb,
      net_profit_rmb: acc.net_profit_rmb + r.net_profit_rmb,
    }),
    { order_count: 0, product_sales_usd: 0, product_sales_rmb: 0, commission_usd: 0, fba_fee_usd: 0, ad_spend_usd: 0, storage_fee_usd: 0, product_cost_rmb: 0, freight_cost_rmb: 0, net_profit_rmb: 0 }
  )

  const columns = [
    {
      title: '产品名称',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 150,
      fixed: 'left',
      ellipsis: true,
      sorter: true,
    },
    {
      title: '颜色',
      dataIndex: 'color',
      key: 'color',
      width: 80,
      render: (val) => val || '-',
    },
    {
      title: 'ASIN',
      dataIndex: 'asin',
      key: 'asin',
      width: 130,
      ellipsis: true,
    },
    {
      title: '销量',
      dataIndex: 'order_count',
      key: 'order_count',
      width: 70,
      align: 'right',
      sorter: true,
    },
    {
      title: '单价(¥)',
      dataIndex: 'cost_rmb',
      key: 'cost_rmb',
      width: 90,
      align: 'right',
      render: (v) => fmtMoney(v),
    },
    {
      title: '运费/台(¥)',
      dataIndex: 'freight_per_unit',
      key: 'freight_per_unit',
      width: 100,
      align: 'right',
      render: (v) => fmtMoney(v),
    },
    {
      title: '销售额($)',
      dataIndex: 'product_sales_usd',
      key: 'product_sales_usd',
      width: 110,
      align: 'right',
      sorter: true,
      render: (v) => fmtMoney(v),
    },
    {
      title: '销售额(¥)',
      dataIndex: 'product_sales_rmb',
      key: 'product_sales_rmb',
      width: 110,
      align: 'right',
      sorter: true,
      render: (v) => fmtMoney(v),
    },
    {
      title: '佣金($)',
      dataIndex: 'commission_usd',
      key: 'commission_usd',
      width: 100,
      align: 'right',
      render: (v) => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span>,
    },
    {
      title: 'FBA($)',
      dataIndex: 'fba_fee_usd',
      key: 'fba_fee_usd',
      width: 90,
      align: 'right',
      render: (v) => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span>,
    },
    {
      title: '广告($)',
      dataIndex: 'ad_spend_usd',
      key: 'ad_spend_usd',
      width: 90,
      align: 'right',
      sorter: true,
      render: (v) => fmtMoney(v),
    },
    {
      title: '仓储+退货+入库($)',
      dataIndex: 'storage_fee_usd',
      key: 'storage_fee_usd',
      width: 140,
      align: 'right',
      render: (v) => fmtMoney(v),
    },
    {
      title: '采购成本(¥)',
      dataIndex: 'product_cost_rmb',
      key: 'product_cost_rmb',
      width: 110,
      align: 'right',
      render: (v) => fmtMoney(v),
    },
    {
      title: '头程运费(¥)',
      dataIndex: 'freight_cost_rmb',
      key: 'freight_cost_rmb',
      width: 110,
      align: 'right',
      render: (v) => fmtMoney(v),
    },
    {
      title: '净利润(¥)',
      dataIndex: 'net_profit_rmb',
      key: 'net_profit_rmb',
      width: 120,
      align: 'right',
      sorter: true,
      fixed: 'right',
      render: (v) => (
        <span style={{ color: v < 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{fmtMoney(v)}</span>
      ),
    },
    {
      title: '净利率',
      dataIndex: 'net_profit_rate',
      key: 'net_profit_rate',
      width: 80,
      align: 'right',
      fixed: 'right',
      render: (v) => (
        <span style={{ color: v < 0 ? '#cf1322' : v > 20 ? '#3f8600' : '#faad14', fontWeight: 500 }}>{fmtRate(v)}</span>
      ),
    },
  ]

  return (
    <div>
      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Select style={{ width: 160 }} value={store || undefined} onChange={setStore} options={storeOptions} placeholder="店铺" showSearch={false} onDropdownVisibleChange={(open) => { if (open) fetchStores() }} />
          <Select style={{ width: 120 }} value={country} onChange={setCountry} options={COUNTRY_OPTIONS} />
          <Select style={{ width: 110 }} value={year} onChange={setYear} options={YEAR_OPTIONS} />
          <Select style={{ width: 100 }} value={month} onChange={setMonth} options={MONTH_OPTIONS} />
          <Input
            placeholder="输入ASIN或产品名称"
            allowClear
            style={{ width: 240 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={handleSearch}
          />
          <Space>
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
            <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
          </Space>
        </div>
      </Card>

      {/* 汇总卡片 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small"><Statistic title="总销量" value={totals.order_count} suffix="台" /></Card>
        </Col>
        <Col span={4}>
          <Card size="small"><Statistic title="销售额($)" value={totals.product_sales_usd} prefix="$" precision={2} /></Card>
        </Col>
        <Col span={4}>
          <Card size="small"><Statistic title="销售额(¥)" value={totals.product_sales_rmb} prefix="¥" precision={2} /></Card>
        </Col>
        <Col span={4}>
          <Card size="small"><Statistic title="广告费($)" value={totals.ad_spend_usd} prefix="$" precision={2} valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
        <Col span={4}>
          <Card size="small"><Statistic title="采购成本(¥)" value={totals.product_cost_rmb} prefix="¥" precision={2} valueStyle={{ color: '#cf1322' }} /></Card>
        </Col>
        <Col span={4}>
          <Card size="small"><Statistic title="净利润(¥)" value={totals.net_profit_rmb} prefix="¥" precision={2} valueStyle={{ color: totals.net_profit_rmb >= 0 ? '#3f8600' : '#cf1322' }} /></Card>
        </Col>
      </Row>

      {/* 数据表格 */}
      <Table
        rowKey={(r) => r.asin}
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={{ ...pagination, showSizeChanger: true, showTotal: (t) => `共 ${t} 个产品` }}
        onChange={handleTableChange}
        scroll={{ x: 2000 }}
        size="small"
        summary={() => {
          if (data.length === 0) return null
          return (
            <Table.Summary fixed>
              <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                <Table.Summary.Cell index={0}>合计</Table.Summary.Cell>
                <Table.Summary.Cell index={1}>-</Table.Summary.Cell>
                <Table.Summary.Cell index={2}>-</Table.Summary.Cell>
                <Table.Summary.Cell index={3} align="right">{totals.order_count}</Table.Summary.Cell>
                <Table.Summary.Cell index={4}>-</Table.Summary.Cell>
                <Table.Summary.Cell index={5}>-</Table.Summary.Cell>
                <Table.Summary.Cell index={6} align="right">{fmtMoney(totals.product_sales_usd)}</Table.Summary.Cell>
                <Table.Summary.Cell index={7} align="right">{fmtMoney(totals.product_sales_rmb)}</Table.Summary.Cell>
                <Table.Summary.Cell index={8} align="right">{fmtMoney(totals.commission_usd)}</Table.Summary.Cell>
                <Table.Summary.Cell index={9} align="right">{fmtMoney(totals.fba_fee_usd)}</Table.Summary.Cell>
                <Table.Summary.Cell index={10} align="right">{fmtMoney(totals.ad_spend_usd)}</Table.Summary.Cell>
                <Table.Summary.Cell index={11} align="right">{fmtMoney(totals.storage_fee_usd)}</Table.Summary.Cell>
                <Table.Summary.Cell index={12} align="right">{fmtMoney(totals.product_cost_rmb)}</Table.Summary.Cell>
                <Table.Summary.Cell index={13} align="right">{fmtMoney(totals.freight_cost_rmb)}</Table.Summary.Cell>
                <Table.Summary.Cell index={14} align="right" style={{ color: totals.net_profit_rmb >= 0 ? '#3f8600' : '#cf1322' }}>{fmtMoney(totals.net_profit_rmb)}</Table.Summary.Cell>
                <Table.Summary.Cell index={15} align="right">{fmtRate(totals.net_profit_rmb / totals.product_sales_rmb * 100)}</Table.Summary.Cell>
              </Table.Summary.Row>
            </Table.Summary>
          )
        }}
      />
    </div>
  )
}
