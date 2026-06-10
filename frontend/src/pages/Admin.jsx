import React, { useState, useEffect } from 'react'
import { Card, Table, Button, Modal, Input, InputNumber, message, Popconfirm, Space, Tabs, Select, Spin } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined, ShopOutlined, GlobalOutlined, DollarOutlined } from '@ant-design/icons'
import { getStores, createStore, deleteStore, getCountries, createCountry, deleteCountry } from '../api'
import axios from 'axios'
const api = axios.create({ baseURL: '/api' })

export default function SystemAdmin() {
  const [tab, setTab] = useState('stores')
  return (
    <Tabs activeKey={tab} onChange={setTab} items={[
      { key: 'stores', label: <><ShopOutlined /> 店铺管理</>, children: <StoreManager /> },
      { key: 'countries', label: <><GlobalOutlined /> 国家管理</>, children: <CountryManager /> },
      { key: 'rates', label: <><DollarOutlined /> 汇率管理</>, children: <RateManager /> },
    ]} />
  )
}

function StoreManager() {
  const [stores, setStores] = useState([]); const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false); const [code, setCode] = useState(''); const [name, setName] = useState(''); const [editing, setEditing] = useState(false)
  const fetch = async () => { setLoading(true); setStores((await getStores()).data||[]); setLoading(false) }
  useEffect(() => { fetch() }, [])
  const save = async () => {
    if (editing) {
      await api.put(`/admin/stores/${code}`, null, { params: { name, new_code: code } })
    } else {
      await createStore(code, name)
    }
    message.success(editing?'已更新':'已创建'); setOpen(false); setEditing(false); fetch()
  }
  return (<Card><Space style={{marginBottom:16}}><Button type="primary" icon={<PlusOutlined/>} onClick={()=>{setEditing(false);setCode('');setName('');setOpen(true)}}>创建店铺</Button></Space>
    <Table rowKey="id" size="small" loading={loading} dataSource={stores} pagination={false}
      columns={[{title:'代码',dataIndex:'code',width:200},{title:'名称',dataIndex:'name'},
        {title:'操作',width:140,render:(_,r)=>(<Space size={0}>
          <Button size="small" icon={<EditOutlined/>} onClick={()=>{setEditing(true);setCode(r.code);setName(r.name);setOpen(true)}}/>
          <Popconfirm title="确定删除？" onConfirm={async()=>{await deleteStore(r.code);fetch()}}><Button danger size="small" icon={<DeleteOutlined/>}/></Popconfirm>
        </Space>)}]}/>
    <Modal title={editing?'编辑店铺':'创建店铺'} open={open} onOk={save} onCancel={()=>setOpen(false)}>
      <div style={{marginBottom:8}}>代码 <Input value={code} onChange={e=>setCode(e.target.value)} placeholder="如 LMG-NA" disabled={editing}/></div>
      <div>名称 <Input value={name} onChange={e=>setName(e.target.value)} placeholder="如 LMG北美站"/></div>
    </Modal></Card>)
}

function CountryManager() {
  const [data, setData] = useState([]); const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false); const [code, setCode] = useState(''); const [name, setName] = useState(''); const [currency,setCurrency]=useState('USD'); const [editing, setEditing] = useState(false)
  const fetch = async () => { setLoading(true); setData((await getCountries()).data||[]); setLoading(false) }
  useEffect(()=>{fetch()},[])
  const save = async () => {
    if (editing) { await api.put(`/admin/countries/${code}`, null, { params: { name, currency } }) }
    else { await api.post('/admin/countries', null, { params: { code: code.toUpperCase(), name, currency } }) }
    message.success(editing?'已更新':'已创建'); setOpen(false); setEditing(false); fetch()
  }
  return (<Card><Space style={{marginBottom:16}}><Button type="primary" icon={<PlusOutlined/>} onClick={()=>{setEditing(false);setCode('');setName('');setCurrency('USD');setOpen(true)}}>创建国家</Button></Space>
    <Table rowKey="id" size="small" loading={loading} dataSource={data} pagination={false}
      columns={[{title:'代码',dataIndex:'code',width:80},{title:'名称',dataIndex:'name',width:150},{title:'货币',dataIndex:'currency',width:80},
        {title:'操作',width:140,render:(_,r)=>(<Space size={0}>
          <Button size="small" icon={<EditOutlined/>} onClick={()=>{setEditing(true);setCode(r.code);setName(r.name);setCurrency(r.currency);setOpen(true)}}/>
          <Popconfirm title="确定删除？" onConfirm={async()=>{await api.delete(`/admin/countries/${r.code}`);fetch()}}><Button danger size="small" icon={<DeleteOutlined/>}/></Popconfirm>
        </Space>)}]}/>
    <Modal title={editing?'编辑国家':'创建国家'} open={open} onOk={save} onCancel={()=>setOpen(false)}>
      <div style={{marginBottom:8}}>代码 <Input value={code} onChange={e=>setCode(e.target.value)} placeholder="如 FR" disabled={editing}/></div>
      <div style={{marginBottom:8}}>名称 <Input value={name} onChange={e=>setName(e.target.value)} placeholder="如 法国站"/></div>
      <div>货币 <Input value={currency} onChange={e=>setCurrency(e.target.value)} placeholder="USD"/></div>
    </Modal></Card>)
}

function RateManager() {
  const [rates, setRates] = useState([]); const [countries, setCountries] = useState([]); const [stores, setStores] = useState([]); const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false); const [editing, setEditing] = useState(false); const [editId, setEditId] = useState(null)
  const [cid, setCid] = useState(null); const [rate, setRate] = useState(0)
  const [selectedStore, setSelectedStore] = useState(null)
  const [selectedYear, setSelectedYear] = useState('2026'); const [selectedMonth, setSelectedMonth] = useState(5)
  const ym = `${selectedYear}-${String(selectedMonth).padStart(2,'0')}`

  const fetchRatesAndStores = async () => {
    setLoading(true)
    const [r, s] = await Promise.all([api.get('/admin/exchange-rates'), api.get('/stores')])
    setRates(r.data||[]); setStores(s.data||[]); setLoading(false)
  }
  useEffect(()=>{fetchRatesAndStores()},[])

  // 根据选中店铺动态加载国家
  useEffect(() => {
    if (selectedStore) {
      api.get(`/stores/${encodeURIComponent(selectedStore)}/countries`).then(res => {
        setCountries(res.data || [])
      })
    } else {
      api.get('/admin/countries').then(res => {
        setCountries(res.data || [])
      })
    }
  }, [selectedStore])

  // 筛选：按店铺+年月
  const filtered = rates.filter(r => {
    if (selectedStore && r.store !== selectedStore) return false
    if (r.year_month !== ym) return false
    return true
  })

  // 构建表格数据：每个国家一行，没有记录的国家也显示
  const tableData = countries.map(c => {
    const existing = filtered.find(r => r.country_code === c.code)
    return {
      key: c.id,
      country_code: c.code,
      country_name: c.name,
      rate: existing ? existing.rate : null,
      id: existing ? existing.id : null,
      hasRate: !!existing,
    }
  })

  const openEdit = (record) => {
    setEditing(true)
    setEditId(record.id)
    setCid(record.key)
    setRate(record.rate || 0)
    setOpen(true)
  }
  const openAdd = (record) => {
    setEditing(false)
    setEditId(null)
    setCid(record ? record.key : countries[0]?.id)
    setRate(0)
    setOpen(true)
  }
  const save = async () => {
    if (editing) {
      await api.put(`/admin/exchange-rates/${editId}`, null, { params: { rate } })
    } else {
      await api.post('/admin/exchange-rates', null, { params: { country_id: cid, year_month: ym, rate, store: selectedStore } })
    }
    message.success(editing ? '已更新' : '已创建')
    setOpen(false); setEditing(false); fetchRatesAndStores()
  }

  return (
    <div>
      {/* 筛选栏 */}
      <div style={{display:'flex',gap:16,marginBottom:16,alignItems:'center'}}>
        <span>店铺</span>
        <Select style={{width:180}} value={selectedStore} onChange={setSelectedStore} allowClear placeholder="全部"
          options={stores.map(s=>({value:s.name,label:s.name}))}/>
        <span style={{marginLeft:16}}>年月</span>
        <Select style={{width:100}} value={selectedYear} onChange={setSelectedYear}
          options={[{value:'2025',label:'2025'},{value:'2026',label:'2026'}]}/>
        <Select style={{width:90}} value={selectedMonth} onChange={setSelectedMonth}
          options={Array.from({length:12},(_,i)=>({value:i+1,label:`${i+1}月`}))}/>
      </div>

      {/* 汇率表 */}
      <Table rowKey="key" size="small" loading={loading} dataSource={tableData} pagination={false}
        columns={[
          {title:'国家',dataIndex:'country_code',width:80,render:(v,r)=><strong>{v}</strong>},
          {title:'名称',dataIndex:'country_name',width:100},
          {title:'汇率 (兑人民币)',dataIndex:'rate',width:150,
            render:(v,r)=> r.hasRate
              ? <span style={{fontSize:16,fontWeight:600}}>{v?.toFixed(4)}</span>
              : <span style={{color:'#ccc'}}>未设置</span>},
          {title:'操作',width:120,render:(_,r)=>(
            r.hasRate
              ? <Space size={0}>
                  <Button size="small" type="link" icon={<EditOutlined/>} onClick={()=>openEdit(r)}>修改</Button>
                  <Popconfirm title="确定删除？" onConfirm={async()=>{await api.delete(`/admin/exchange-rates/${r.id}`);fetchRatesAndStores()}}>
                    <Button size="small" type="link" danger icon={<DeleteOutlined/>}>删除</Button>
                  </Popconfirm>
                </Space>
              : <Button size="small" type="link" icon={<PlusOutlined/>} onClick={()=>openAdd(r)}>设置</Button>
          )},
        ]}/>

      {/* 编辑弹窗 */}
      <Modal title={editing ? '修改汇率' : '设置汇率'} open={open} onOk={save} onCancel={()=>setOpen(false)}
        okText="保存" cancelText="取消">
        <div style={{marginBottom:12}}>
          <span>国家：</span>
          <strong>{countries.find(c=>c.id===cid)?.code} {countries.find(c=>c.id===cid)?.name}</strong>
        </div>
        <div style={{marginBottom:12}}>
          <span>年月：</span><strong>{ym}</strong>
        </div>
        <div>
          <span>汇率：</span>
          <InputNumber value={rate} onChange={setRate} step={0.01} style={{width:200}} autoFocus/>
          <span style={{marginLeft:8,color:'#999'}}>→ RMB</span>
        </div>
      </Modal>
    </div>
  )
}
