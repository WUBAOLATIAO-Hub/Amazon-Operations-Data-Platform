import React, { useState, useEffect } from 'react'
import { Card, Table, Button, Modal, Input, InputNumber, message, Popconfirm, Space, Tabs, Select, Spin, Switch, Tag } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined, ShopOutlined, GlobalOutlined, DollarOutlined, ReloadOutlined, UserOutlined } from '@ant-design/icons'
import {
  getStores, createStore, updateStore, deleteStore,
  getCountries, createCountry, updateCountry, deleteCountry,
  getExchangeRates, createExchangeRate, updateExchangeRate, deleteExchangeRate,
  getStoreCountries, recalculateProfit,
  getUsers, createUser, updateUser, deleteUser,
} from '../api'
import { useAuth } from '../contexts/AuthContext'

export default function SystemAdmin() {
  const [tab, setTab] = useState('stores')
  const { user } = useAuth()

  const tabs = [
    { key: 'stores', label: <><ShopOutlined /> 店铺管理</>, children: <StoreManager /> },
    { key: 'countries', label: <><GlobalOutlined /> 国家管理</>, children: <CountryManager /> },
    { key: 'rates', label: <><DollarOutlined /> 汇率管理</>, children: <RateManager /> },
    { key: 'tools', label: <><ReloadOutlined /> 数据工具</>, children: <DataTools /> },
  ]

  // 管理员才显示用户管理
  if (user?.is_admin) {
    tabs.push({ key: 'users', label: <><UserOutlined /> 用户管理</>, children: <UserManager /> })
  }

  return (
    <Tabs activeKey={tab} onChange={setTab} items={tabs} />
  )
}

function StoreManager() {
  const [stores, setStores] = useState([]); const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false); const [code, setCode] = useState(''); const [name, setName] = useState(''); const [editing, setEditing] = useState(false)
  const fetch = async () => { setLoading(true); setStores((await getStores()).data||[]); setLoading(false) }
  useEffect(() => { fetch() }, [])
  const save = async () => {
    if (editing) {
      await updateStore(code, name, code)
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
  const [open, setOpen] = useState(false); const [code, setCode] = useState(''); const [name, setName] = useState(''); const [editing, setEditing] = useState(false)
  const fetch = async () => { setLoading(true); setData((await getCountries()).data||[]); setLoading(false) }
  useEffect(()=>{fetch()},[])
  const save = async () => {
    if (editing) { await updateCountry(code, name) }
    else { await createCountry(code.toUpperCase(), name) }
    message.success(editing?'已更新':'已创建'); setOpen(false); setEditing(false); fetch()
  }
  return (<Card><Space style={{marginBottom:16}}><Button type="primary" icon={<PlusOutlined/>} onClick={()=>{setEditing(false);setCode('');setName('');setOpen(true)}}>创建国家</Button></Space>
    <Table rowKey="id" size="small" loading={loading} dataSource={data} pagination={false}
      columns={[{title:'代码',dataIndex:'code',width:80},{title:'名称',dataIndex:'name',width:150},
        {title:'操作',width:140,render:(_,r)=>(<Space size={0}>
          <Button size="small" icon={<EditOutlined/>} onClick={()=>{setEditing(true);setCode(r.code);setName(r.name);setOpen(true)}}/>
          <Popconfirm title="确定删除？" onConfirm={async()=>{await deleteCountry(r.code);fetch()}}><Button danger size="small" icon={<DeleteOutlined/>}/></Popconfirm>
        </Space>)}]}/>
    <Modal title={editing?'编辑国家':'创建国家'} open={open} onOk={save} onCancel={()=>setOpen(false)}>
      <div style={{marginBottom:8}}>代码 <Input value={code} onChange={e=>setCode(e.target.value)} placeholder="如 FR" disabled={editing}/></div>
      <div>名称 <Input value={name} onChange={e=>setName(e.target.value)} placeholder="如 法国站"/></div>
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
    const [r, s] = await Promise.all([getExchangeRates(), getStores()])
    setRates(r.data||[]); setStores(s.data||[]); setLoading(false)
  }
  useEffect(()=>{fetchRatesAndStores()},[])

  useEffect(() => {
    if (selectedStore) {
      getStoreCountries(selectedStore).then(res => { setCountries(res.data || []) })
    } else {
      getCountries().then(res => { setCountries(res.data || []) })
    }
  }, [selectedStore])

  const filtered = rates.filter(r => {
    if (selectedStore && r.store !== selectedStore) return false
    if (r.year_month !== ym) return false
    return true
  })

  const tableData = countries.map(c => {
    const existing = filtered.find(r => r.country_code === c.code)
    return {
      key: c.id, country_code: c.code, country_name: c.name,
      rate: existing ? existing.rate : null, id: existing ? existing.id : null, hasRate: !!existing,
    }
  })

  const openEdit = (record) => { setEditing(true); setEditId(record.id); setCid(record.key); setRate(record.rate || 0); setOpen(true) }
  const openAdd = (record) => { setEditing(false); setEditId(null); setCid(record ? record.key : countries[0]?.id); setRate(0); setOpen(true) }
  const save = async () => {
    if (editing) { await updateExchangeRate(editId, rate) }
    else { await createExchangeRate(cid, ym, rate, selectedStore) }
    message.success(editing ? '已更新' : '已创建')
    setOpen(false); setEditing(false); fetchRatesAndStores()
  }

  return (
    <div>
      <div style={{display:'flex',gap:16,marginBottom:16,alignItems:'center'}}>
        <span>店铺</span>
        <Select style={{width:180}} value={selectedStore} onChange={setSelectedStore} allowClear placeholder="全部"
          options={stores.map(s=>({value:s.name,label:s.name}))}/>
        <span style={{marginLeft:16}}>年月</span>
        <Select style={{width:100}} value={selectedYear} onChange={setSelectedYear}
          options={[2025,2026,2027,2028,2029,2030].map(y=>({value:String(y),label:String(y)}))}/>
        <Select style={{width:90}} value={selectedMonth} onChange={setSelectedMonth}
          options={Array.from({length:12},(_,i)=>({value:i+1,label:`${i+1}月`}))}/>
      </div>
      <Table rowKey="key" size="small" loading={loading} dataSource={tableData} pagination={false}
        columns={[
          {title:'国家',dataIndex:'country_code',width:80,render:(v,r)=><strong>{v}</strong>},
          {title:'名称',dataIndex:'country_name',width:100},
          {title:'汇率 (兑人民币)',dataIndex:'rate',width:150,
            render:(v,r)=> r.hasRate ? <span style={{fontSize:16,fontWeight:600}}>{v?.toFixed(4)}</span> : <span style={{color:'#ccc'}}>未设置</span>},
          {title:'操作',width:120,render:(_,r)=>(
            r.hasRate
              ? <Space size={0}>
                  <Button size="small" type="link" icon={<EditOutlined/>} onClick={()=>openEdit(r)}>修改</Button>
                  <Popconfirm title="确定删除？" onConfirm={async()=>{await deleteExchangeRate(r.id);fetchRatesAndStores()}}>
                    <Button size="small" type="link" danger icon={<DeleteOutlined/>}>删除</Button>
                  </Popconfirm>
                </Space>
              : <Button size="small" type="link" icon={<PlusOutlined/>} onClick={()=>openAdd(r)}>设置</Button>
          )},
        ]}/>
      <Modal title={editing ? '修改汇率' : '设置汇率'} open={open} onOk={save} onCancel={()=>setOpen(false)} okText="保存" cancelText="取消">
        <div style={{marginBottom:12}}><span>国家：</span><strong>{countries.find(c=>c.id===cid)?.code} {countries.find(c=>c.id===cid)?.name}</strong></div>
        <div style={{marginBottom:12}}><span>年月：</span><strong>{ym}</strong></div>
        <div><span>汇率：</span><InputNumber value={rate} onChange={setRate} step={0.01} style={{width:200}} autoFocus/><span style={{marginLeft:8,color:'#999'}}>→ RMB</span></div>
      </Modal>
    </div>
  )
}

function DataTools() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)

  const handleRecalculate = async (country) => {
    setLoading(true)
    try {
      const res = await recalculateProfit(country || null)
      if (res.data.detail) { message.error(res.data.detail) }
      else { setResults(res.data.results); message.success(res.data.message || '重算完成') }
    } catch (e) { message.error('重算失败: ' + (e.response?.data?.detail || e.message)) }
    setLoading(false)
  }

  return (
    <Card title="数据重算工具" extra={<Spin spinning={loading} />}>
      <p style={{marginBottom:16,color:'#666'}}>
        修改汇率或修复数据后，点击下方按钮重新计算所有产品的净利润。<br/>数据量大时可能需要等待 10-30 秒。
      </p>
      <Space>
        <Button type="primary" icon={<ReloadOutlined/>} loading={loading} onClick={()=>handleRecalculate()}>重算全部国家</Button>
      </Space>
      {results && (
        <Table rowKey="country" size="small" style={{marginTop:16}} dataSource={Object.entries(results).map(([k,v])=>({country:k,...v}))} pagination={false}
          columns={[
            {title:'国家',dataIndex:'country',width:80},
            {title:'销售额(RMB)',dataIndex:'sales_rmb',width:150,render:v=>v?.toLocaleString()},
            {title:'净利润(RMB)',dataIndex:'net_profit_rmb',width:150,render:v=><span style={{color:v>=0?'#52c41a':'#ff4d4f',fontWeight:600}}>{v?.toLocaleString()}</span>},
            {title:'记录数',dataIndex:'summary_count',width:100},
          ]}/>
      )}
    </Card>
  )
}

function UserManager() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editUser, setEditUser] = useState(null)
  const [editPassword, setEditPassword] = useState('')
  const [editIsAdmin, setEditIsAdmin] = useState(false)

  const fetch = async () => {
    setLoading(true)
    try { setUsers(await getUsers()) } catch (e) { /* ignore */ }
    setLoading(false)
  }
  useEffect(() => { fetch() }, [])

  const handleCreate = async () => {
    if (!username || !password) { message.warning('请填写用户名和密码'); return }
    try {
      await createUser({ username, password, is_admin: isAdmin })
      message.success('用户创建成功')
      setOpen(false); setUsername(''); setPassword(''); setIsAdmin(false); fetch()
    } catch (e) {
      message.error(e.response?.data?.detail || '创建失败')
    }
  }

  const handleUpdate = async () => {
    if (!editUser) return
    try {
      const data = { is_admin: editIsAdmin }
      if (editPassword) data.password = editPassword
      await updateUser(editUser.id, data)
      message.success('更新成功')
      setEditOpen(false); setEditUser(null); setEditPassword(''); fetch()
    } catch (e) {
      message.error(e.response?.data?.detail || '更新失败')
    }
  }

  const handleDelete = async (userId) => {
    try {
      await deleteUser(userId)
      message.success('已删除'); fetch()
    } catch (e) {
      message.error(e.response?.data?.detail || '删除失败')
    }
  }

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>创建用户</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} dataSource={users} pagination={false}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '用户名', dataIndex: 'username', width: 200 },
          { title: '角色', dataIndex: 'is_admin', width: 120,
            render: (v) => v ? <Tag color="red">管理员</Tag> : <Tag color="blue">普通用户</Tag> },
          { title: '创建时间', dataIndex: 'created_at', width: 200 },
          { title: '操作', width: 200, render: (_, r) => (
            <Space size={0}>
              <Button size="small" icon={<EditOutlined />} onClick={() => {
                setEditUser(r); setEditPassword(''); setEditIsAdmin(!!r.is_admin); setEditOpen(true)
              }}>编辑</Button>
              {r.username !== 'admin' && (
                <Popconfirm title="确定删除？" onConfirm={() => handleDelete(r.id)}>
                  <Button danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>
              )}
            </Space>
          )},
        ]} />

      {/* 创建用户弹窗 */}
      <Modal title="创建用户" open={open} onOk={handleCreate} onCancel={() => setOpen(false)}>
        <div style={{ marginBottom: 12 }}>
          <span>用户名：</span>
          <Input value={username} onChange={e => setUsername(e.target.value)} placeholder="输入用户名" />
        </div>
        <div style={{ marginBottom: 12 }}>
          <span>密码：</span>
          <Input.Password value={password} onChange={e => setPassword(e.target.value)} placeholder="输入密码" />
        </div>
        <div>
          <span>管理员权限：</span>
          <Switch checked={isAdmin} onChange={setIsAdmin} style={{ marginLeft: 8 }} />
        </div>
      </Modal>

      {/* 编辑用户弹窗 */}
      <Modal title="编辑用户" open={editOpen} onOk={handleUpdate} onCancel={() => setEditOpen(false)}>
        <div style={{ marginBottom: 12 }}>
          <span>用户名：</span>
          <strong>{editUser?.username}</strong>
        </div>
        <div style={{ marginBottom: 12 }}>
          <span>新密码（留空不修改）：</span>
          <Input.Password value={editPassword} onChange={e => setEditPassword(e.target.value)} placeholder="留空则不修改" />
        </div>
        <div>
          <span>管理员权限：</span>
          <Switch checked={editIsAdmin} onChange={setEditIsAdmin} disabled={editUser?.username === 'admin'} style={{ marginLeft: 8 }} />
        </div>
      </Modal>
    </Card>
  )
}
