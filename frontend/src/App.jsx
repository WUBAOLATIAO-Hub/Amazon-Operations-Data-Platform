import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Advertising from './pages/Advertising'
import DataImport from './pages/DataImport'
import DataQuery from './pages/DataQuery'
import SystemAdmin from './pages/Admin'

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="advertising" element={<Advertising />} />
            <Route path="import" element={<DataImport />} />
            <Route path="query" element={<DataQuery />} />
            <Route path="admin" element={<SystemAdmin />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
