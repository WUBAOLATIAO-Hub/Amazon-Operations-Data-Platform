import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：自动带上 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 自动跳转登录
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// 看板
export const getDashboardSummary = (params) => api.get('/dashboard/summary', { params })
export const getDashboardTrend = (params) => api.get('/dashboard/trend', { params })
export const getProductDistribution = (params) => api.get('/dashboard/product-distribution', { params })
export const getCostBreakdown = (params) => api.get('/dashboard/cost-breakdown', { params })
export const getTopReturns = (params) => api.get('/dashboard/top-returns', { params })
export const getStoreComparison = (params) => api.get('/dashboard/store-comparison', { params })
export const getCountryComparison = (params) => api.get('/dashboard/country-comparison', { params })
export const getTransferSummary = (params) => api.get('/dashboard/transfer-summary', { params })

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
export const getMonthlySummary = (params, config) => api.get('/query/monthly-summary', { params, ...config })
export const getCountrySummary = (params, config) => api.get('/query/country-summary', { params, ...config })

// 导出
export const exportMonthlySummary = (params) => api.get('/export/monthly-summary', { params, responseType: 'blob' })
export const exportCountrySummary = (params) => api.get('/export/country-summary', { params, responseType: 'blob' })

// 认证
export const authLogin = async (username, password) => {
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)
  const res = await api.post('/auth/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}
export const authMe = async () => {
  const res = await api.get('/auth/me')
  return res.data
}
export const authChangePassword = (data) => api.post('/auth/change-password', data)

// 用户管理（管理员）
export const getUsers = async () => {
  const res = await api.get('/auth/users')
  return res.data
}
export const createUser = async (data) => {
  const res = await api.post('/auth/users', data)
  return res.data
}
export const updateUser = async (userId, data) => {
  const res = await api.put(`/auth/users/${userId}`, data)
  return res.data
}
export const deleteUser = async (userId) => {
  const res = await api.delete(`/auth/users/${userId}`)
  return res.data
}

export default api
