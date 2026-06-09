import React, { useState, useEffect, useRef } from 'react'
import { Select, Input, Button, Table, Card, message, Space, Statistic, Row, Col, Segmented, Tag } from 'antd'
import { SearchOutlined, ReloadOutlined, TableOutlined, AppstoreOutlined } from '@ant-design/icons'
import { getMonthlySummary, getCountrySummary, getStores, getCountries } from '../api'

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
  const [country, setCountry] = useState('')
  const [year, setYear] = useState(2026)
  const [month, setMonth] = useState(0)
  const [store, setStore] = useState('')
  const [storeOptions, setStoreOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState([{ value: '', label: '全部国家' }])
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState([])
  const [totals, setTotals] = useState({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [sorter, setSorter] = useState({})
  const [viewMode, setViewMode] = useState('compact')

  // 国家汇总
  const [countryData, setCountryData] = useState([])
  const [countryLoading, setCountryLoading] = useState(false)

  const keywordRef = useRef(keyword)
  keywordRef.current = keyword

  // 拉取国家汇总
  const fetchCountrySummary = async () => {
    if (!store || country) { setCountryData([]); return }
    setCountryLoading(true)
    try {
      const params = { store }
      if (year) params.year = year
      if (month) params.month = month
      const res = await getCountrySummary(params)
      setCountryData(res.data?.data || [])
    } catch {
      setCountryData([])
    } finally {
      setCountryLoading(false)
    }
  }

  // 拉取产品明细
  const fetchData = async (page = 1, pageSize = 50, sortField, sortOrder) => {
    setLoading(true)
    try {
      const kw = keywordRef.current.trim()
      const params = { page, page_size: pageSize }
      if (country) params.country = country
      if (store) params.store = store
      if (year) params.year = year
      if (month) params.month = month
      if (kw) params.keyword = kw
      if (sortField) params.sort_by = sortField
      if (sortOrder) params.sort_order = sortOrder === 'ascend' ? 'asc' : 'desc'

      const res = await getMonthlySummary(params)
      const result = res.data
      setData(result.data || [])
      setTotals(result.totals || {})
      setPagination((prev) => ({ ...prev, current: page, pageSize, total: result.total || 0 }))
    } catch (err) {
      message.error('查询失败：' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    getCountries().then(res => {
      const opts = [{ value: '', label: '全部国家' }, ...(res.data || []).map(c => ({ value: c.code, label: `${c.code} ${c.name}` }))]
      setCountryOptions(opts)
    }).catch(() => {})
    getStores().then(res => {
      const opts = (res.data || []).map(s => ({ value: s.code, label: s.name }))
      setStoreOptions(opts)
      if (opts.length > 0) setStore(opts[0].value)
    }).catch(() => {})
  }, [])

  // 筛选条件变化时自动查询
  useEffect(() => {
    if (store) {
      fetchData(1, pagination.pageSize, sorter.field, sorter.order)
      fetchCountrySummary()
    }
  }, [store, country, year, month])

  const handleSearch = () => {
    fetchData(1, pagination.pageSize, sorter.field, sorter.order)
    fetchCountrySummary()
  }

  const handleReset = () => {
    setKeyword('')
    setCountry('')
    setYear(2026)
    setMonth(0)
    keywordRef.current = ''
    // useEffect 会自动触发查询
  }

  const handleTableChange = (pag, _, newSorter) => {
    setSorter(newSorter)
    fetchData(pag.current, pag.pageSize, newSorter.field, newSorter.order)
  }

  // 点击国家行 → 筛选该国家（useEffect 会自动触发查询）
  const handleCountryRow = (countryCode) => {
    setCountry(countryCode)
  }

  // 国家汇总表列
  const countryColumns = [
    { title: '国家', dataIndex: 'country_name', width: 100, render: (v, r) => <Tag>{r.country_code}</Tag> },
    { title: '销量', dataIndex: 'order_count', width: 70, align: 'right', render: v => <strong>{v}</strong> },
    { title: '销售额($)', dataIndex: 'product_sales_usd', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '销售额(¥)', dataIndex: 'product_sales_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '佣金($)', dataIndex: 'commission_usd', width: 100, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span> },
    { title: 'FBA($)', dataIndex: 'fba_fee_usd', width: 90, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span> },
    { title: '广告($)', dataIndex: 'ad_spend_usd', width: 90, align: 'right', render: v => fmtMoney(v) },
    { title: '仓储+退货+入库($)', dataIndex: 'storage_fee_usd', width: 150, align: 'right', render: (_, r) => fmtMoney(r.storage_fee_usd + r.returns_fee_usd + r.inbound_fee_usd) },
    { title: '采购成本(¥)', dataIndex: 'product_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '头程运费(¥)', dataIndex: 'freight_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '净利润(¥)', dataIndex: 'net_profit_rmb', width: 120, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{fmtMoney(v)}</span> },
    { title: '净利率', dataIndex: 'net_profit_rate', width: 80, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : v > 20 ? '#3f8600' : '#faad14', fontWeight: 500 }}>{fmtRate(v)}</span> },
    { title: '占比', dataIndex: 'sales_pct', width: 70, align: 'right', render: v => <span style={{ color: '#666' }}>{v}%</span> },
  ]

  // 产品明细表列 - 精简模式
  const compactColumns = [
    { title: '产品名称', dataIndex: 'product_name', key: 'product_name', width: 180, fixed: 'left', ellipsis: true, sorter: true },
    { title: 'ASIN', dataIndex: 'asin', key: 'asin', width: 130, ellipsis: true },
    { title: '颜色', dataIndex: 'color', key: 'color', width: 70, render: v => v || '-' },
    { title: '销量', dataIndex: 'order_count', key: 'order_count', width: 70, align: 'right', sorter: true, render: v => <strong>{v}</strong> },
    { title: '单价(¥)', dataIndex: 'cost_rmb', key: 'cost_rmb', width: 90, align: 'right', render: v => fmtMoney(v) },
    { title: '运费/台(¥)', dataIndex: 'freight_per_unit', key: 'freight_per_unit', width: 100, align: 'right', render: v => fmtMoney(v) },
    { title: '销售额(¥)', dataIndex: 'product_sales_rmb', key: 'product_sales_rmb', width: 110, align: 'right', sorter: true, render: v => fmtMoney(v) },
    { title: '采购成本(¥)', dataIndex: 'product_cost_rmb', key: 'product_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '头程运费(¥)', dataIndex: 'freight_cost_rmb', key: 'freight_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '净利润(¥)', dataIndex: 'net_profit_rmb', key: 'net_profit_rmb', width: 120, align: 'right', sorter: true, fixed: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{fmtMoney(v)}</span> },
    { title: '净利率', dataIndex: 'net_profit_rate', key: 'net_profit_rate', width: 80, align: 'right', fixed: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : v > 20 ? '#3f8600' : '#faad14', fontWeight: 500 }}>{fmtRate(v)}</span> },
  ]

  // 产品明细表列 - 完整模式
  const fullColumns = [
    ...compactColumns.slice(0, 4),
    { title: '单价(¥)', dataIndex: 'cost_rmb', key: 'cost_rmb', width: 90, align: 'right', render: v => fmtMoney(v) },
    { title: '运费/台(¥)', dataIndex: 'freight_per_unit', key: 'freight_per_unit', width: 100, align: 'right', render: v => fmtMoney(v) },
    { title: '销售额($)', dataIndex: 'product_sales_usd', key: 'product_sales_usd', width: 110, align: 'right', sorter: true, render: v => fmtMoney(v) },
    { title: '销售额(¥)', dataIndex: 'product_sales_rmb', key: 'product_sales_rmb', width: 110, align: 'right', sorter: true, render: v => fmtMoney(v) },
    { title: '佣金($)', dataIndex: 'commission_usd', key: 'commission_usd', width: 100, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span> },
    { title: 'FBA($)', dataIndex: 'fba_fee_usd', key: 'fba_fee_usd', width: 90, align: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : undefined }}>{fmtMoney(v)}</span> },
    { title: '广告($)', dataIndex: 'ad_spend_usd', key: 'ad_spend_usd', width: 90, align: 'right', sorter: true, render: v => fmtMoney(v) },
    { title: '仓储+退货+入库($)', dataIndex: 'storage_fee_usd', key: 'storage_fee_usd', width: 150, align: 'right', render: v => fmtMoney(v) },
    { title: '采购成本(¥)', dataIndex: 'product_cost_rmb', key: 'product_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '头程运费(¥)', dataIndex: 'freight_cost_rmb', key: 'freight_cost_rmb', width: 110, align: 'right', render: v => fmtMoney(v) },
    { title: '净利润(¥)', dataIndex: 'net_profit_rmb', key: 'net_profit_rmb', width: 120, align: 'right', sorter: true, fixed: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : '#3f8600', fontWeight: 600 }}>{fmtMoney(v)}</span> },
    { title: '净利率', dataIndex: 'net_profit_rate', key: 'net_profit_rate', width: 80, align: 'right', fixed: 'right', render: v => <span style={{ color: v < 0 ? '#cf1322' : v > 20 ? '#3f8600' : '#faad14', fontWeight: 500 }}>{fmtRate(v)}</span> },
  ]

  const columns = viewMode === 'compact' ? compactColumns : fullColumns

  return (
    <div>
      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Select style={{ width: 160 }} value={store} onChange={setStore} options={storeOptions} placeholder="选择店铺" showSearch />
          <Select style={{ width: 140 }} value={country} onChange={setCountry} options={countryOptions} />
          <Select style={{ width: 110 }} value={year} onChange={setYear} options={YEAR_OPTIONS} />
          <Select style={{ width: 100 }} value={month} onChange={setMonth} options={MONTH_OPTIONS} />
          <Input placeholder="ASIN或产品名称" allowClear style={{ width: 200 }} value={keyword} onChange={e => setKeyword(e.target.value)} onPressEnter={handleSearch} />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
        </div>
      </Card>

      {/* 店铺汇总卡片 */}
      <Row gutter={10} style={{ marginBottom: 12 }}>
        <Col span={4}><Card size="small"><Statistic title="总销量" value={totals.order_count || 0} suffix="台" /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="销售额($)" value={totals.product_sales_usd || 0} prefix="$" precision={2} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="销售额(¥)" value={totals.product_sales_rmb || 0} prefix="¥" precision={2} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="佣金($)" value={totals.commission_usd || 0} prefix="$" precision={2} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="FBA($)" value={totals.fba_fee_usd || 0} prefix="$" precision={2} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="广告($)" value={totals.ad_spend_usd || 0} prefix="$" precision={2} valueStyle={{ color: '#faad14' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="净利润(¥)" value={totals.net_profit_rmb || 0} prefix="¥" precision={2} valueStyle={{ color: (totals.net_profit_rmb || 0) >= 0 ? '#3f8600' : '#cf1322' }} /></Card></Col>
      </Row>

      {/* 国家汇总表（选了"全部国家"时显示） */}
      {!country && countryData.length > 0 && (
        <Card size="small" title="国家汇总" style={{ marginBottom: 12 }} extra={<span style={{ color: '#999', fontSize: 12 }}>点击行查看该国家产品明细</span>}>
          <Table
            rowKey="country_code"
            size="small"
            loading={countryLoading}
            dataSource={countryData}
            pagination={false}
            scroll={{ x: 1200 }}
            onRow={(record) => ({ onClick: () => handleCountryRow(record.country_code), style: { cursor: 'pointer' } })}
            columns={countryColumns}
            summary={() => {
              if (countryData.length === 0) return null
              const t = countryData.reduce((acc, r) => ({
                order_count: acc.order_count + r.order_count,
                product_sales_usd: acc.product_sales_usd + r.product_sales_usd,
                product_sales_rmb: acc.product_sales_rmb + r.product_sales_rmb,
                net_profit_rmb: acc.net_profit_rmb + r.net_profit_rmb,
              }), { order_count: 0, product_sales_usd: 0, product_sales_rmb: 0, net_profit_rmb: 0 })
              return (
                <Table.Summary fixed>
                  <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                    <Table.Summary.Cell index={0}>合计</Table.Summary.Cell>
                    <Table.Summary.Cell index={1} align="right">{t.order_count}</Table.Summary.Cell>
                    <Table.Summary.Cell index={2} align="right">{fmtMoney(t.product_sales_usd)}</Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">{fmtMoney(t.product_sales_rmb)}</Table.Summary.Cell>
                    <Table.Summary.Cell index={4}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={5}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={6}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={7}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={8}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={9}>-</Table.Summary.Cell>
                    <Table.Summary.Cell index={10} align="right" style={{ color: t.net_profit_rmb >= 0 ? '#3f8600' : '#cf1322' }}>{fmtMoney(t.net_profit_rmb)}</Table.Summary.Cell>
                    <Table.Summary.Cell index={11} align="right">{fmtRate(t.net_profit_rmb / t.product_sales_rmb * 100)}</Table.Summary.Cell>
                    <Table.Summary.Cell index={12}>100%</Table.Summary.Cell>
                  </Table.Summary.Row>
                </Table.Summary>
              )
            }}
          />
        </Card>
      )}

      {/* 产品明细表 */}
      <Card
        size="small"
        title={<span>产品明细 {country && <Tag color="blue" closable onClose={() => setCountry('')}>{country}</Tag>}</span>}
        extra={
          <Segmented
            size="small"
            value={viewMode}
            onChange={setViewMode}
            options={[
              { value: 'compact', icon: <AppstoreOutlined />, label: '精简' },
              { value: 'full', icon: <TableOutlined />, label: '完整' },
            ]}
          />
        }
      >
        <Table
          rowKey={r => `${r.asin}-${r.sku}`}
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={{ ...pagination, showSizeChanger: true, showTotal: t => `共 ${t} 个产品` }}
          onChange={handleTableChange}
          scroll={{ x: viewMode === 'compact' ? 1200 : 2000 }}
          size="small"
          summary={() => {
            if (data.length === 0) return null
            const t = data.reduce((acc, r) => ({
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
            }), { order_count: 0, product_sales_usd: 0, product_sales_rmb: 0, commission_usd: 0, fba_fee_usd: 0, ad_spend_usd: 0, storage_fee_usd: 0, product_cost_rmb: 0, freight_cost_rmb: 0, net_profit_rmb: 0 })
            return (
              <Table.Summary fixed>
                <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                  <Table.Summary.Cell index={0}>本页合计</Table.Summary.Cell>
                  {viewMode === 'compact' ? (
                    <>
                      <Table.Summary.Cell index={1}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={2}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={3} align="right">{t.order_count}</Table.Summary.Cell>
                      <Table.Summary.Cell index={4}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={5}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={6} align="right">{fmtMoney(t.product_sales_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={7} align="right">{fmtMoney(t.product_cost_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={8} align="right">{fmtMoney(t.freight_cost_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={9} align="right" style={{ color: t.net_profit_rmb >= 0 ? '#3f8600' : '#cf1322' }}>{fmtMoney(t.net_profit_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={10} align="right">{fmtRate(t.net_profit_rmb / t.product_sales_rmb * 100)}</Table.Summary.Cell>
                    </>
                  ) : (
                    <>
                      <Table.Summary.Cell index={1}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={2}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={3} align="right">{t.order_count}</Table.Summary.Cell>
                      <Table.Summary.Cell index={4}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={5}>-</Table.Summary.Cell>
                      <Table.Summary.Cell index={6} align="right">{fmtMoney(t.product_sales_usd)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={7} align="right">{fmtMoney(t.product_sales_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={8} align="right">{fmtMoney(t.commission_usd)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={9} align="right">{fmtMoney(t.fba_fee_usd)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={10} align="right">{fmtMoney(t.ad_spend_usd)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={11} align="right">{fmtMoney(t.storage_fee_usd)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={12} align="right">{fmtMoney(t.product_cost_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={13} align="right">{fmtMoney(t.freight_cost_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={14} align="right" style={{ color: t.net_profit_rmb >= 0 ? '#3f8600' : '#cf1322' }}>{fmtMoney(t.net_profit_rmb)}</Table.Summary.Cell>
                      <Table.Summary.Cell index={15} align="right">{fmtRate(t.net_profit_rmb / t.product_sales_rmb * 100)}</Table.Summary.Cell>
                    </>
                  )}
                </Table.Summary.Row>
              </Table.Summary>
            )
          }}
        />
      </Card>
    </div>
  )
}
