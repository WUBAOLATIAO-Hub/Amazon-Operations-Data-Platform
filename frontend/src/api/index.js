import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 看板
export const getDashboardSummary = (params) => api.get('/dashboard/summary', { params })
export const getDashboardTrend = (params) => api.get('/dashboard/trend', { params })
export const getProductDistribution = (params) => api.get('/dashboard/product-distribution', { params })
export const getCostBreakdown = (params) => api.get('/dashboard/cost-breakdown', { params })

// 广告
export const getAdvertisingSummary = (params) => api.get('/advertising/summary', { params })
export const getAdvertisingDetail = (params) => api.get('/advertising/detail', { params })

// 导入
export const getImportSupported = () => api.get('/import/supported')
export const uploadFile = (type, file, country, store, year, month) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('country', country || 'auto')
  if (store) formData.append('store', store)
  if (year) formData.append('import_year', year)
  if (month) formData.append('import_month', month)
  return api.post(`/import/${type}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 一键导入工作簿
export const uploadWorkbook = (file, country = 'auto', store, year, month) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('country', country)
  if (store) formData.append('store', store)
  if (year) formData.append('import_year', year)
  if (month) formData.append('import_month', month)
  return api.post('/import/workbook', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000
  })
}

// 店铺
export const getStores = () => api.get('/stores')
export const createStore = (code, name) => api.post('/admin/stores', null, { params: { code, name } })
export const updateStore = (code, name, new_code) => api.put(`/admin/stores/${code}`, null, { params: { name, new_code } })
export const deleteStore = (code) => api.delete(`/admin/stores/${code}`)
export const getStoreCountries = (storeName) => api.get(`/stores/${encodeURIComponent(storeName)}/countries`)

// 国家管理
export const getCountries = () => api.get('/admin/countries')
export const createCountry = (code, name) => api.post('/admin/countries', null, { params: { code, name } })
export const updateCountry = (code, name) => api.put(`/admin/countries/${code}`, null, { params: { name } })
export const deleteCountry = (code) => api.delete(`/admin/countries/${code}`)

// 汇率管理
export const getExchangeRates = () => api.get('/admin/exchange-rates')
export const createExchangeRate = (country_id, year_month, rate, store) =>
  api.post('/admin/exchange-rates', null, { params: { country_id, year_month, rate, store } })
export const updateExchangeRate = (id, rate) => api.put(`/admin/exchange-rates/${id}`, null, { params: { rate } })
export const deleteExchangeRate = (id) => api.delete(`/admin/exchange-rates/${id}`)

// 重算利润
export const recalculateProfit = (country) => api.post('/import/recalculate', null, { params: country ? { country } : {} })

// 查询
export const getMonthlySummary = (params) => api.get('/query/monthly-summary', { params })
export const getCountrySummary = (params) => api.get('/query/country-summary', { params })

export default api
