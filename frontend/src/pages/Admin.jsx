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
  const [rates, setRates] = useState([]); const [countries, setCountries] = useState([]); const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false); const [cid, setCid] = useState(1); const [ym, setYm] = useState('2026-05'); const [rate, setRate] = useState(6.8); const [editing, setEditing] = useState(false); const [editId, setEditId] = useState(null)
  const fetch = async () => { setLoading(true); const [r, c] = await Promise.all([api.get('/admin/exchange-rates'), api.get('/admin/countries')]); setRates(r.data||[]); setCountries(c.data||[]); setLoading(false) }
  useEffect(()=>{fetch()},[])
  const save = async () => {
    if (editing) { await api.put(`/admin/exchange-rates/${editId}`, null, { params: { rate } }) }
    else { await api.post('/admin/exchange-rates', null, { params: { country_id: cid, year_month: ym, rate } }) }
    message.success(editing?'已更新':'已创建'); setOpen(false); setEditing(false); fetch()
  }

  // Group rates by country
  const grouped = {}
  for (const r of rates) {
    if (!grouped[r.country_code]) grouped[r.country_code] = []
    grouped[r.country_code].push(r)
  }
  // Sort each country's rates by year_month desc
  for (const k of Object.keys(grouped)) {
    grouped[k].sort((a,b) => b.year_month.localeCompare(a.year_month))
  }

  return (
    <div>
      <Space style={{marginBottom:16}}><Button type="primary" icon={<PlusOutlined/>} onClick={()=>{setEditing(false);setOpen(true)}}>添加汇率</Button></Space>
      {loading ? <Spin /> : Object.keys(grouped).map(cc => {
        const countryInfo = countries.find(c=>c.code===cc)
        return (
          <Card key={cc} size="small" title={<span><GlobalOutlined style={{marginRight:8}}/>{cc} {countryInfo?.name||''}</span>} style={{marginBottom:12}}>
            <Table rowKey="id" size="small" dataSource={grouped[cc]} pagination={false} showHeader={false}
              columns={[
                {title:'年月',dataIndex:'year_month',width:120,render:v=><strong>{v}</strong>},
                {title:'汇率',dataIndex:'rate',width:120,render:v=>v?.toFixed(4)},
                {title:'操作',width:120,render:(_,r)=>(<Space size={0}>
                   <Button size="small" icon={<EditOutlined/>} onClick={()=>{setEditing(true);setEditId(r.id);setRate(r.rate);setOpen(true)}}/>
                   <Popconfirm title="确定删除？" onConfirm={async()=>{await api.delete(`/admin/exchange-rates/${r.id}`);fetch()}}><Button danger size="small" icon={<DeleteOutlined/>}/></Popconfirm>
                 </Space>)}
              ]}/>
          </Card>
        )
      })}
      <Modal title={editing?'编辑汇率':'添加汇率'} open={open} onOk={save} onCancel={()=>setOpen(false)}>
        {!editing && <div style={{marginBottom:8}}>国家 <Select style={{width:'100%'}} value={cid} onChange={setCid} options={countries.map(c=>({value:c.id,label:c.code+' '+c.name}))}/></div>}
        {!editing && <div style={{marginBottom:8,display:'flex',gap:8,alignItems:'center'}}>
          <span>年月</span>
          <Select style={{width:100}} value={ym.substring(0,4)} onChange={y=>setYm(y+'-'+ym.substring(5))} options={[{value:'2025',label:'2025'},{value:'2026',label:'2026'}]}/>
          <Select style={{width:80}} value={parseInt(ym.substring(5))} onChange={m=>setYm(ym.substring(0,4)+'-'+String(m).padStart(2,'0'))} options={Array.from({length:12},(_,i)=>({value:i+1,label:(i+1)+'月'}))}/>
        </div>}
        <div>汇率 <InputNumber value={rate} onChange={setRate} step={0.01} style={{width:'100%'}}/></div>
      </Modal>
    </div>
  )
}
