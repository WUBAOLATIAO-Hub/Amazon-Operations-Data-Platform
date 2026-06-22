import React, { useState, useEffect, useCallback } from 'react'
import { Row, Col, Select, Card, Table, Statistic, Spin, message } from 'antd'
import { AimOutlined, LineChartOutlined } from '@ant-design/icons'
import { getAdvertisingSummary, getAdvertisingDetail, getStores, getCountries } from '../api'

// 年份选项
const YEAR_OPTIONS = [
  { value: 0, label: '全部' },
  { value: 2025, label: '2025年' },
  { value: 2026, label: '2026年' },
  { value: 2027, label: '2027年' },
  { value: 2028, label: '2028年' },
  { value: 2029, label: '2029年' },
  { value: 2030, label: '2030年' },
]
const MONTH_OPTIONS = [
  { value: 0, label: '全部' },
  ...Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` })),
]

/** 格式化金额 */
function formatMoney(num, decimals = 2) {
  if (num === null || num === undefined) return '0.00'
  return Number(num).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

/** 格式化百分比 */
function formatPercent(num) {
  if (num === null || num === undefined) return '0.00'
  return Number(num).toFixed(2)
}

/** 格式化整数千分位 */
function formatInt(num) {
  if (num === null || num === undefined) return '0'
  return Number(num).toLocaleString('en-US')
}

export default function Advertising() {
  const [country, setCountry] = useState('')
  const [store, setStore] = useState('')
  const [storeOptions, setStoreOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState([])
  const [adYear, setAdYear] = useState(2026)
  const [adMonth, setAdMonth] = useState(5)

  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState(null)
  const [detailData, setDetailData] = useState([])
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [sorter, setSorter] = useState({})

  // 获取店铺和国家
  useEffect(() => {
    getStores().then(res => {
      setStoreOptions([{value:'',label:'全部店铺'},...(res.data||[]).map(s=>({value:s.code,label:s.name}))])
    }).catch(()=>{})
    getCountries().then(res => {
      setCountryOptions([{value:'',label:'全部国家'},...(res.data||[]).map(c=>({value:c.code,label:c.name}))])
    }).catch(()=>{})
  }, [])

  // 获取汇总数据
  const fetchSummary = useCallback(async () => {
    try {
      const params = { country }
      if (adYear) params.year = adYear
      if (adMonth) params.month = adMonth
      if (store) params.store = store
      const res = await getAdvertisingSummary(params)
      setSummary(res.data)
    } catch (err) {
      message.error('获取广告汇总失败：' + (err.response?.data?.detail || err.message))
    }
  }, [country, store, adYear, adMonth])

  // 获取明细数据
  const fetchDetail = useCallback(async (page = 1, pageSize = 20, sortField, sortOrder) => {
    setLoading(true)
    try {
      const params = {
        country,
        year: adYear,
        month: adMonth,
        page,
        page_size: pageSize,
      }
      if (store) params.store = store
      if (sortField && sortOrder) {
        params.sort_by = sortField
        params.sort_order = sortOrder === 'ascend' ? 'asc' : 'desc'
      }
      const res = await getAdvertisingDetail(params)
      const data = res.data
      setDetailData(data.items || data.data || data || [])
      setPagination((prev) => ({
        ...prev,
        current: page,
        pageSize,
        total: data.total || (data.items || data.data || []).length,
      }))
    } catch (err) {
      message.error('获取广告明细失败：' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }, [country, store, adYear, adMonth])

  // 初始加载 & 筛选变化时加载
  useEffect(() => {
    fetchSummary()
    fetchDetail(1, pagination.pageSize)
  }, [fetchSummary, fetchDetail])

  // 表格列定义
  const columns = [
    {
      title: '产品名',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 200,
      ellipsis: true,
      sorter: true,
    },
    {
      title: 'ASIN',
      dataIndex: 'asin',
      key: 'asin',
      width: 130,
      sorter: true,
    },
    {
      title: '花费 (RMB)',
      dataIndex: 'ad_spend',
      key: 'ad_spend',
      width: 120,
      align: 'right',
      sorter: true,
      render: (val) => `¥${formatMoney(val)}`,
    },
    {
      title: '销售额 (RMB)',
      dataIndex: 'ad_sales',
      key: 'ad_sales',
      width: 130,
      align: 'right',
      sorter: true,
      render: (val) => `¥${formatMoney(val)}`,
    },
    {
      title: 'ACOS',
      dataIndex: 'acos',
      key: 'acos',
      width: 100,
      align: 'right',
      sorter: true,
      render: (val) => `${formatPercent(val)}%`,
    },
    {
      title: 'ROAS',
      dataIndex: 'roas',
      key: 'roas',
      width: 100,
      align: 'right',
      sorter: true,
      render: (val) => formatPercent(val),
    },
    {
      title: 'CTR',
      dataIndex: 'ctr',
      key: 'ctr',
      width: 90,
      align: 'right',
      sorter: true,
      render: (val) => `${formatPercent(val)}%`,
    },
    {
      title: 'CPC',
      dataIndex: 'cpc',
      key: 'cpc',
      width: 90,
      align: 'right',
      sorter: true,
      render: (val) => `¥${formatMoney(val)}`,
    },
    {
      title: '展示次数',
      dataIndex: 'impressions',
      key: 'impressions',
      width: 110,
      align: 'right',
      sorter: true,
      render: (val) => formatInt(val),
    },
    {
      title: '点击量',
      dataIndex: 'clicks',
      key: 'clicks',
      width: 90,
      align: 'right',
      sorter: true,
      render: (val) => formatInt(val),
    },
    {
      title: '订单数',
      dataIndex: 'ad_orders',
      key: 'ad_orders',
      width: 90,
      align: 'right',
      sorter: true,
      render: (val) => formatInt(val),
    },
    {
      title: '转化率',
      dataIndex: 'conversion_rate',
      key: 'conversion_rate',
      width: 100,
      align: 'right',
      sorter: true,
      render: (val) => `${formatPercent(val)}%`,
    },
  ]

  // 表格变更（排序、分页）
  const handleTableChange = (pag, filters, newSorter) => {
    setSorter(newSorter)
    const page = pag.current
    const pageSize = pag.pageSize
    fetchDetail(page, pageSize, newSorter.field, newSorter.order)
  }

  // 行样式：ACOS 高的行红色高亮
  const rowClassName = (record) => {
    const acos = record.acos ?? record.Acos ?? 0
    if (acos > 50) return 'row-high-acos'
    return ''
  }

  return (
    <div>
      <style>{`
        .row-high-acos > td {
          background: #fff1f0 !important;
        }
        .row-high-acos:hover > td {
          background: #ffccc7 !important;
        }
      `}</style>

      {/* 筛选栏 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <Select style={{ width: 160 }} value={store} onChange={setStore} options={storeOptions} placeholder="全部店铺" />
        <Select style={{ width: 140 }} value={country} onChange={setCountry}
          options={countryOptions} placeholder="全部国家" />
        <Select style={{ width: 110 }} value={adYear} onChange={setAdYear} options={YEAR_OPTIONS} />
        <Select style={{ width: 90 }} value={adMonth} onChange={setAdMonth} options={MONTH_OPTIONS} />
      </div>

      {/* 汇总卡片 */}
      <Spin spinning={loading && !summary}>
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={8}>
            <Card hoverable>
              <Statistic
                title="总花费 (RMB)"
                value={summary?.total_ad_spend ?? 0}
                precision={2}
                prefix="¥"
                valueStyle={{ color: '#cf1322' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card hoverable>
              <Statistic
                title="平均 ACOS"
                value={summary?.avg_acos ?? 0}
                precision={2}
                suffix="%"
                prefix={<AimOutlined />}
                valueStyle={{ color: '#faad14' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card hoverable>
              <Statistic
                title="平均 ROAS"
                value={summary?.avg_roas ?? 0}
                precision={2}
                prefix={<LineChartOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>

      {/* 明细表格 */}
      <Card title="广告明细">
        <Table
          rowKey={(record) => record.asin + (record.campaign_id || record.id || '')}
          columns={columns}
          dataSource={detailData}
          loading={loading}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
          rowClassName={rowClassName}
          scroll={{ x: 1400 }}
          size="middle"
        />
      </Card>
    </div>
  )
}
