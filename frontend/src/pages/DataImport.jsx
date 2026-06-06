import React, { useState, useEffect } from 'react'
import { Select, Tabs, Upload, Card, Alert, Descriptions, Spin, message, Typography, Space, Tag, Collapse, Input } from 'antd'
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from '@ant-design/icons'
import { getImportSupported, uploadFile, uploadWorkbook } from '../api'

const { Dragger } = Upload
const { Text, Title } = Typography

// 国家选项
const COUNTRY_OPTIONS = [
  { value: 'US', label: '美国站' },
  { value: 'UK', label: '英国站' },
  { value: 'DE', label: '德国站' },
  { value: 'JP', label: '日本站' },
  { value: 'CA', label: '加拿大站' },
]

// 6 种导入类型
const IMPORT_TABS = [
  { key: 'transactions', label: '交易数据', accept: '.csv,.xlsx', icon: '📊' },
  { key: 'products', label: '产品信息', accept: '.csv,.xlsx', icon: '📦' },
  { key: 'advertising', label: '广告数据', accept: '.csv,.xlsx', icon: '📢' },
  { key: 'storage', label: '仓储费', accept: '.csv,.xlsx', icon: '🏬' },
  { key: 'returns', label: '退货费', accept: '.csv,.xlsx', icon: '↩️' },
  { key: 'inbound', label: '入库费', accept: '.csv,.xlsx', icon: '📥' },
]

export default function DataImport() {
  const [country, setCountry] = useState('US')
  const [store, setStore] = useState('')
  const [activeTab, setActiveTab] = useState('transactions')

  // 各类型的上传状态
  const [uploading, setUploading] = useState({}) // { [type]: boolean }
  const [results, setResults] = useState({})     // { [type]: { success, skipped, errors } }

  // 工作簿导入状态
  const [wbUploading, setWbUploading] = useState(false)
  const [wbResult, setWbResult] = useState(null)

  // 支持的字段信息
  const [supportedInfo, setSupportedInfo] = useState({})
  const [loadingSupported, setLoadingSupported] = useState(false)

  // 获取支持的字段信息
  useEffect(() => {
    setLoadingSupported(true)
    getImportSupported()
      .then((res) => {
        setSupportedInfo(res.data || {})
      })
      .catch((err) => {
        // 静默失败，字段说明非必需
        console.warn('获取导入支持信息失败', err)
      })
      .finally(() => setLoadingSupported(false))
  }, [])

  // 上传文件前校验
  const beforeUpload = (file, type) => {
    const isCSV = file.name.endsWith('.csv')
    const isXLSX = file.name.endsWith('.xlsx')
    if (!isCSV && !isXLSX) {
      message.error('仅支持 .csv 或 .xlsx 格式文件')
      return Upload.LIST_IGNORE
    }
    const isLt100M = file.size / 1024 / 1024 < 100
    if (!isLt100M) {
      message.error('文件大小不能超过 100MB')
      return Upload.LIST_IGNORE
    }
    return true
  }

  // 自定义上传
  const handleUpload = async ({ file, onSuccess, onError }, type) => {
    setUploading((prev) => ({ ...prev, [type]: true }))
    try {
      const res = await uploadFile(type, file, country, store)
      const data = res.data
      setResults((prev) => ({
        ...prev,
        [type]: {
          success: data.imported ?? data.success ?? 0,
          skipped: data.skipped ?? 0,
          errors: data.errors ?? [],
          fileName: file.name,
        },
      }))
      message.success(`${file.name} 导入完成`)
      onSuccess(data)
    } catch (err) {
      const errMsg = err.response?.data?.detail || err.message
      setResults((prev) => ({
        ...prev,
        [type]: {
          success: 0,
          skipped: 0,
          errors: [errMsg],
          fileName: file.name,
        },
      }))
      message.error(`导入失败：${errMsg}`)
      onError(err)
    } finally {
      setUploading((prev) => ({ ...prev, [type]: false }))
    }
  }

  // 获取当前 tab 的支持字段
  const getCurrentFields = () => {
    const info = supportedInfo[activeTab]
    if (!info) return null
    // info 可能是 { fields: [...], description: '...' } 或数组
    if (Array.isArray(info)) return info
    return info.fields || info.columns || null
  }

  // 渲染导入结果
  const renderResult = (type) => {
    const result = results[type]
    if (!result) return null

    const hasErrors = result.errors && result.errors.length > 0

    return (
      <div style={{ marginTop: 16 }}>
        <Alert
          type={hasErrors ? 'warning' : 'success'}
          showIcon
          icon={hasErrors ? <WarningOutlined /> : <CheckCircleOutlined />}
          message={
            <Space>
              <Text strong>{result.fileName}</Text>
              <Tag color="green">成功: {result.success}</Tag>
              <Tag color="orange">跳过: {result.skipped}</Tag>
              {hasErrors && <Tag color="red">错误: {result.errors.length}</Tag>}
            </Space>
          }
          style={{ marginBottom: hasErrors ? 8 : 0 }}
        />
        {hasErrors && (
          <Card size="small" style={{ marginTop: 8, maxHeight: 200, overflow: 'auto' }}>
            {result.errors.slice(0, 20).map((err, idx) => (
              <div key={idx} style={{ color: '#cf1322', fontSize: 13, padding: '2px 0' }}>
                <CloseCircleOutlined style={{ marginRight: 6 }} />
                {typeof err === 'string' ? err : err.message || JSON.stringify(err)}
              </div>
            ))}
            {result.errors.length > 20 && (
              <Text type="secondary">...还有 {result.errors.length - 20} 条错误</Text>
            )}
          </Card>
        )}
      </div>
    )
  }

  // 渲染单个 Tab 内容
  const renderTabContent = (tab) => {
    const isUploading = uploading[tab.key] || false

    return (
      <div>
        {/* 拖拽上传 */}
        <Dragger
          name="file"
          multiple={false}
          accept={tab.accept}
          showUploadList={false}
          beforeUpload={(file) => beforeUpload(file, tab.key)}
          customRequest={(options) => handleUpload(options, tab.key)}
          disabled={isUploading}
          style={{ padding: '24px 0' }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text" style={{ fontSize: 16 }}>
            {isUploading ? '正在上传...' : `点击或拖拽文件到此区域上传`}
          </p>
          <p className="ant-upload-hint">
            支持 {tab.accept} 格式，单文件最大 100MB
          </p>
        </Dragger>

        {/* 导入结果 */}
        {renderResult(tab.key)}

        {/* 字段说明 */}
        <Card
          size="small"
          title="支持的字段说明"
          style={{ marginTop: 16 }}
          loading={loadingSupported}
        >
          {(() => {
            const fields = getCurrentFields()
            if (!fields) {
              return <Text type="secondary">暂无字段说明，请确保文件包含标准列头。</Text>
            }
            if (Array.isArray(fields)) {
              return (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {fields.map((f, idx) => {
                    const name = typeof f === 'string' ? f : f.name || f.field
                    const desc = typeof f === 'object' ? f.description || f.desc : ''
                    return (
                      <Tag key={idx} color="blue">
                        {name}
                        {desc && <Text type="secondary" style={{ marginLeft: 4, fontSize: 12 }}>({desc})</Text>}
                      </Tag>
                    )
                  })}
                </div>
              )
            }
            return <Text type="secondary">{JSON.stringify(fields)}</Text>
          })()}
        </Card>
      </div>
    )
  }

  // 工作簿上传处理
  const handleWorkbookUpload = async ({ file, onSuccess, onError }) => {
    setWbUploading(true)
    setWbResult(null)
    try {
      const res = await uploadWorkbook(file, country, store)
      setWbResult(res.data)
      message.success('工作簿导入完成')
      onSuccess(res.data)
    } catch (err) {
      const errMsg = err.response?.data?.detail || err.message
      setWbResult({ detail: errMsg })
      message.error(`导入失败：${errMsg}`)
      onError(err)
    } finally {
      setWbUploading(false)
    }
  }

  // 渲染工作簿导入结果
  const renderWorkbookResult = () => {
    if (!wbResult) return null
    if (wbResult.detail) {
      return <Alert type="error" showIcon message={wbResult.detail} style={{ marginTop: 16 }} />
    }

    const sheets = wbResult.sheets || {}
    const items = Object.entries(sheets).map(([name, info]) => ({
      key: name,
      label: (
        <Space>
          <Tag color={info.status === 'success' ? 'green' : info.status === 'skipped' ? 'orange' : 'red'}>
            {info.status === 'success' ? '✅' : info.status === 'skipped' ? '⏭️' : '❌'}
          </Tag>
          <span>{name}</span>
          {info.type && <Tag color="blue">{info.type}</Tag>}
        </Space>
      ),
      children: (
        <div>
          {info.status === 'success' && (
            <Space wrap>
              {info.raw_rows !== undefined && <Tag>原始记录: {info.raw_rows}</Tag>}
              {info.summary_rows !== undefined && <Tag>汇总记录: {info.summary_rows}</Tag>}
              {info.rows !== undefined && <Tag>记录数: {info.rows}</Tag>}
              {info.csv_rows !== undefined && <Tag>数据行: {info.csv_rows}</Tag>}
              {info.summary_updated !== undefined && <Tag>更新汇总: {info.summary_updated}</Tag>}
            </Space>
          )}
          {info.status === 'skipped' && <Text type="secondary">{info.reason}</Text>}
          {info.status === 'error' && <Text type="danger">{info.detail}</Text>}
        </div>
      ),
    }))

    return (
      <div style={{ marginTop: 16 }}>
        <Alert
          type="success"
          showIcon
          message={`工作簿导入完成 - 国家: ${wbResult.country}`}
          style={{ marginBottom: 12 }}
        />
        <Collapse items={items} defaultActiveKey={Object.keys(sheets).filter(k => sheets[k].status === 'success')} />
      </div>
    )
  }

  // 构建 Tabs items
  const tabItems = [
    {
      key: 'workbook',
      label: <span>📋 一键导入工作簿</span>,
      children: (
        <div>
          <Alert
            message="上传合并工作簿（如 美国站全部数据.xlsx），系统自动识别每个 Sheet 并导入所有数据"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Dragger
            name="file"
            multiple={false}
            accept=".xlsx"
            showUploadList={false}
            beforeUpload={(file) => {
              if (!file.name.endsWith('.xlsx')) {
                message.error('仅支持 .xlsx 格式')
                return Upload.LIST_IGNORE
              }
              return true
            }}
            customRequest={handleWorkbookUpload}
            disabled={wbUploading}
            style={{ padding: '24px 0' }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text" style={{ fontSize: 16 }}>
              {wbUploading ? '正在导入...' : '点击或拖拽工作簿文件到此区域'}
            </p>
            <p className="ant-upload-hint">
              支持 .xlsx 格式，自动识别交易/产品/广告/仓储/退货/入库等 Sheet
            </p>
          </Dragger>
          {renderWorkbookResult()}
        </div>
      ),
    },
    ...IMPORT_TABS.map((tab) => ({
      key: tab.key,
      label: (
        <span>
          {tab.icon} {tab.label}
        </span>
      ),
      children: renderTabContent(tab),
    })),
  ]

  return (
    <div>
      {/* 国家选择 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 16, alignItems: 'center' }}>
        <span style={{ fontWeight: 500 }}>数据国家：</span>
        <Select
          style={{ width: 160 }}
          value={country}
          onChange={setCountry}
          options={COUNTRY_OPTIONS}
        />
        <span style={{ fontWeight: 500 }}>店铺名称：</span>
        <Input
          style={{ width: 200 }}
          value={store}
          onChange={(e) => setStore(e.target.value)}
          placeholder="输入店铺名称"
          allowClear
        />
      </div>

      {/* Tabs */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        tabPosition="top"
        destroyInactiveTabPane={false}
      />
    </div>
  )
}
