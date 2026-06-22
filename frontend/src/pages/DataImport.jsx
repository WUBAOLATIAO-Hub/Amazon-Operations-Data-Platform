import React, { useState, useEffect } from 'react'
import { Select, Tabs, Upload, Card, Alert, Spin, message, Typography, Space, Tag, Button, Collapse, Modal } from 'antd'
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined, WarningOutlined } from '@ant-design/icons'
import { getImportSupported, uploadFile, uploadWorkbook, uploadFolder, getStores, getCountries } from '../api'
import axios from 'axios'

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
  const [storeOptions, setStoreOptions] = useState([])
  const [countryOptions, setCountryOptions] = useState([])
  const [importYear, setImportYear] = useState(2026)
  const [importMonth, setImportMonth] = useState(5)
  const [activeTab, setActiveTab] = useState('transactions')

  // 各类型的上传状态
  const [uploading, setUploading] = useState({}) // { [type]: boolean }
  const [results, setResults] = useState({})     // { [type]: { success, skipped, errors } }

  // 工作簿导入状态
  const [wbUploading, setWbUploading] = useState(false)
  const [wbResult, setWbResult] = useState(null)

  // 文件夹批量导入状态
  const [folderUploading, setFolderUploading] = useState(false)
  const [folderResult, setFolderResult] = useState(null)
  const [folderYear, setFolderYear] = useState(2026)

  // 支持的字段信息
  const [supportedInfo, setSupportedInfo] = useState({})
  const [loadingSupported, setLoadingSupported] = useState(false)

  // 获取店铺和国家列表
  useEffect(() => {
    getStores().then(res => {
      const opts = (res.data || []).map(s => ({ value: s.code, label: s.name }))
      setStoreOptions(opts)
      if (opts.length > 0 && !store) setStore(opts[0].value)
    }).catch(() => {})
    getCountries().then(res => {
      const opts = (res.data || []).map(c => ({ value: c.code, label: c.name }))
      setCountryOptions(opts)
      if (opts.length > 0 && !country) setCountry(opts[0].value)
    }).catch(() => {})
  }, [])

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

  // 执行实际导入
  const doUpload = async ({ file, onSuccess, onError }, type) => {
    setUploading((prev) => ({ ...prev, [type]: true }))
    try {
      const res = await uploadFile(type, file, country, store, importYear, importMonth)
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

  // 自定义上传（带二次确认）
  const handleUpload = (options, type) => {
    const { file } = options
    const storeLabel = storeOptions.find(s => s.value === store)?.label || store || '未选择'
    const tabLabel = IMPORT_TABS.find(t => t.key === type)?.label || type

    Modal.confirm({
      title: '确认导入数据',
      icon: <WarningOutlined />,
      content: (
        <div style={{ lineHeight: 2 }}>
          <div><strong>文件：</strong>{file.name}</div>
          <div><strong>类型：</strong>{tabLabel}</div>
          <div><strong>店铺：</strong>{storeLabel}</div>
          <div><strong>月份：</strong>{importYear}年{importMonth}月</div>
          <div style={{ color: '#cf1322', marginTop: 8 }}>
            ⚠️ 导入会覆盖该店铺该月份的同类数据，请确认信息无误！
          </div>
        </div>
      ),
      okText: '确认导入',
      cancelText: '取消',
      onOk: () => doUpload(options, type),
      onCancel: () => {
        options.onError(new Error('用户取消'))
      },
    })
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
          multiple={true}
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

  // 执行实际工作簿导入
  const doWorkbookUpload = async ({ file, onSuccess, onError }) => {
    setWbUploading(true)
    setWbResult(null)
    try {
      const res = await uploadWorkbook(file, 'auto', store, importYear, importMonth)
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

  // 工作簿上传处理（带二次确认）
  const handleWorkbookUpload = (options) => {
    const { file } = options
    const storeLabel = storeOptions.find(s => s.value === store)?.label || store || '未选择'

    Modal.confirm({
      title: '确认导入工作簿',
      icon: <WarningOutlined />,
      content: (
        <div style={{ lineHeight: 2 }}>
          <div><strong>文件：</strong>{file.name}</div>
          <div><strong>类型：</strong>一键导入工作簿（多Sheet）</div>
          <div><strong>店铺：</strong>{storeLabel}</div>
          <div><strong>月份：</strong>{importYear}年{importMonth}月</div>
          <div style={{ color: '#cf1322', marginTop: 8 }}>
            ⚠️ 系统将自动识别所有Sheet并导入，会覆盖对应数据，请确认信息无误！
          </div>
        </div>
      ),
      okText: '确认导入',
      cancelText: '取消',
      onOk: () => doWorkbookUpload(options),
      onCancel: () => {
        options.onError(new Error('用户取消'))
      },
    })
  }

  // 渲染工作簿导入结果
  const renderWorkbookResult = () => {
    if (!wbResult) return null
    if (wbResult.detail) {
      return <Alert type="error" showIcon message={wbResult.detail} style={{ marginTop: 16 }} />
    }

    const sheets = wbResult.sheets || {}
    const countrySummary = wbResult.country_summary || {}

    const sheetItems = Object.entries(sheets).map(([name, info]) => ({
      key: name,
      label: (
        <Space>
          <Tag color={info.status === 'success' ? 'green' : info.status === 'skipped' ? 'orange' : 'red'}>
            {info.status === 'success' ? '✅' : info.status === 'skipped' ? '⏭️' : '❌'}
          </Tag>
          <span>{name}</span>
          {info.type && <Tag color="blue">{info.type}</Tag>}
          {info.country && <Tag color="purple">{info.country}</Tag>}
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
          message={`工作簿导入完成 - 国家: ${(wbResult.countries || [wbResult.country]).join(', ')}`}
          style={{ marginBottom: 12 }}
        />
        {/* 国家汇总卡片 */}
        {Object.keys(countrySummary).length > 0 && (
          <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
            {Object.entries(countrySummary).map(([cc, s]) => (
              <Card key={cc} size="small" style={{ flex: 1, minWidth: 200 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{cc}</div>
                <div style={{ fontSize: 12, lineHeight: 1.8 }}>
                  订单: {s.order_count} (raw {s.raw_orders}单/{s.raw_refunds}退款)<br/>
                  销售额: ${s.sales_usd?.toLocaleString()}<br/>
                  广告: ${s.ad_spend_usd?.toLocaleString()}<br/>
                  仓储: ${s.storage_fee_usd?.toLocaleString()}<br/>
                  净利润: {s.net_profit_rmb?.toLocaleString()} RMB
                </div>
              </Card>
            ))}
          </div>
        )}
        <Collapse items={sheetItems} defaultActiveKey={Object.keys(sheets).filter(k => sheets[k].status === 'success')} />
      </div>
    )
  }

  // 文件夹批量导入处理
  const handleFolderUpload = async (options) => {
    const { fileList, onSuccess, onError } = options
    if (!fileList || fileList.length === 0) {
      onError(new Error('请选择文件夹'))
      return
    }
    setFolderUploading(true)
    setFolderResult(null)
    try {
      const files = fileList.map(f => f.originFileObj || f)
      const res = await uploadFolder(files, folderYear)
      setFolderResult(res.data)
      message.success('文件夹批量导入完成')
      onSuccess(res.data)
    } catch (err) {
      const errMsg = err.response?.data?.detail || err.message
      if (errMsg !== 'canceled') message.error('导入失败：' + errMsg)
      onError(err)
    } finally {
      setFolderUploading(false)
    }
  }

  // 文件夹导入结果渲染
  const renderFolderResult = () => {
    if (!folderResult) return null
    if (folderResult.detail) {
      return <Alert type="error" showIcon message={folderResult.detail} style={{ marginTop: 16 }} />
    }
    const { message: msg, files_processed, skipped, results } = folderResult
    const items = []
    if (results) {
      Object.entries(results).forEach(([key, r]) => {
        const status = r.status === 'success' ? 'success' : r.status === 'error' ? 'error' : 'warning'
        items.push({ key, result: r, status })
      })
    }
    return (
      <div style={{ marginTop: 16 }}>
        <Alert type={files_processed > 0 ? 'success' : 'warning'} showIcon 
          message={`${msg || '导入完成'} - 处理 ${files_processed || 0} 个文件`}
          style={{ marginBottom: 8 }} />
        {skipped && skipped.length > 0 && (
          <Alert type="warning" showIcon style={{ marginBottom: 8 }}
            message={`跳过 ${skipped.length} 个文件：${skipped.map(s => s.file).join(', ')}`} />
        )}
        {items.length > 0 && (
          <Collapse size="small" items={[{
            key: 'details', label: `明细 (${items.length} 项)`,
            children: items.map(({ key, result: r, status }) => (
              <div key={key} style={{ marginBottom: 4, display: 'flex', gap: 8 }}>
                <Tag color={status === 'success' ? 'green' : status === 'error' ? 'red' : 'orange'}>
                  {status === 'success' ? '成功' : status === 'error' ? '失败' : '跳过'}
                </Tag>
                <span>{key}</span>
                {r.type && <Tag>{r.type}</Tag>}
                {r.rows && <span style={{color:'#999',fontSize:12}}>{r.rows}行</span>}
                {r.error && <span style={{color:'red',fontSize:12}}>{r.error}</span>}
              </div>
            ))
          }]} />
        )}
      </div>
    )
  }

  // 构建 Tabs items
  const tabItems = [
    {
      key: 'folder',
      label: <span>📂 文件夹批量导入</span>,
      children: (
        <div>
          <Alert
            message="选择文件夹（如 04/），系统自动从文件名解析店铺和月份（如 LMG-EU_04.xlsx → LMG-EU 04月）"
            type="info" showIcon style={{ marginBottom: 12 }} />
          <div style={{ marginBottom: 12, display: 'flex', gap: 16, alignItems: 'center' }}>
            <span style={{ fontWeight: 500 }}>导入年份：</span>
            <Select style={{ width: 100 }} value={folderYear} onChange={setFolderYear}
              options={[2025,2026,2027,2028,2029,2030].map(y=>({value:y,label:y+'年'}))} />
            <span style={{ color: '#999', fontSize: 12 }}>月份从文件名自动解析（_04 → 4月）</span>
          </div>
          <input
            type="file"
            webkitdirectory=""
            directory=""
            multiple
            accept=".xlsx,.csv"
            style={{ display: 'none' }}
            id="folder-input"
            onChange={async (e) => {
              const fileList = Array.from(e.target.files || [])
              if (fileList.length === 0) return
              handleFolderUpload({ fileList: fileList.map(f => ({ originFileObj: f })), onSuccess: () => {}, onError: () => {} })
              e.target.value = ''
            }}
          />
          <div
            onClick={() => document.getElementById('folder-input').click()}
            style={{
              border: '2px dashed #d9d9d9', borderRadius: 8, padding: '40px 24px',
              textAlign: 'center', cursor: folderUploading ? 'not-allowed' : 'pointer',
              background: folderUploading ? '#f5f5f5' : '#fafafa',
              opacity: folderUploading ? 0.6 : 1
            }}
          >
            <p style={{ fontSize: 48, color: '#1677ff', margin: '0 0 8px 0' }}>📂</p>
            <p style={{ fontSize: 16, margin: 0 }}>
              {folderUploading ? '正在导入...' : '点击选择文件夹'}
            </p>
            <p style={{ color: '#999', marginTop: 4 }}>
              文件命名格式：{'店铺代码_月份.xlsx'}，如 MGT-EU_04.xlsx
            </p>
          </div>
          {renderFolderResult()}
        </div>
      ),
    },
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
      <div style={{ marginBottom: 24, display: 'flex', gap: 16, alignItems: 'center' }}>
        <span style={{ fontWeight: 500 }}>店铺：</span>
        <Select style={{ width: 180 }} value={store || undefined} onChange={setStore} options={storeOptions} placeholder="选择店铺" />
        <span style={{ fontWeight: 500 }}>导入月份：</span>
        <Select style={{ width: 100 }} value={importYear} onChange={setImportYear}
          options={[2025,2026,2027,2028,2029,2030].map(y=>({value:y,label:y+'年'}))} />
        <Select style={{ width: 80 }} value={importMonth} onChange={setImportMonth}
          options={Array.from({length:12},(_,i)=>({value:i+1,label:`${i+1}月`}))} />
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
