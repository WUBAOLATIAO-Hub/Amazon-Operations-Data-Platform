import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 看板
export const getDashboardSummary = (params) => api.get('/dashboard/summary', { params })
export const getDashboardTrend = (params) => api.get('/dashboard/trend', { params })
export const getProductDistribution = (params) => api.get('/dashboard/product-distribution', { params })

// 广告
export const getAdvertisingSummary = (params) => api.get('/advertising/summary', { params })
export const getAdvertisingDetail = (params) => api.get('/advertising/detail', { params })

// 导入
export const getImportSupported = () => api.get('/import/supported')
export const uploadFile = (type, file, country, store) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('country', country)
  if (store) formData.append('store', store)
  return api.post(`/import/${type}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 一键导入工作簿
export const uploadWorkbook = (file, country = 'US', store) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('country', country)
  if (store) formData.append('store', store)
  return api.post('/import/workbook', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000
  })
}

// 店铺
export const getStores = (country) => api.get('/stores', { params: { country } })

// 查询
export const getMonthlySummary = (params) => api.get('/query/monthly-summary', { params })
export const getTransactions = (params) => api.get('/query/transactions', { params })

export default api
