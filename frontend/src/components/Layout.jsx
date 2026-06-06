import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, theme } from 'antd'
import {
  DashboardOutlined,
  BarChartOutlined,
  ImportOutlined,
  SearchOutlined,
} from '@ant-design/icons'

const { Sider, Content, Header } = AntLayout

const menuItems = [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: '数据看板',
  },
  {
    key: '/advertising',
    icon: <BarChartOutlined />,
    label: '广告分析',
  },
  {
    key: '/import',
    icon: <ImportOutlined />,
    label: '数据导入',
  },
  {
    key: '/query',
    icon: <SearchOutlined />,
    label: '数据查询',
  },
]

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken()

  const onMenuClick = ({ key }) => {
    navigate(key)
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={200}
        theme="dark"
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
        }}
      >
        <div
          style={{
            height: 48,
            margin: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: collapsed ? 14 : 18,
            fontWeight: 700,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            letterSpacing: 1,
          }}
        >
          {collapsed ? 'LMG' : 'LMG 数据平台'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={onMenuClick}
        />
      </Sider>
      <AntLayout style={{ marginLeft: collapsed ? 80 : 200, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <span style={{ fontSize: 16, fontWeight: 500 }}>
            {menuItems.find((item) => item.key === location.pathname)?.label || 'LMG 数据平台'}
          </span>
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: '#fff',
            borderRadius: borderRadiusLG,
            minHeight: 280,
            border: '1px solid #f0f0f0',
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}
