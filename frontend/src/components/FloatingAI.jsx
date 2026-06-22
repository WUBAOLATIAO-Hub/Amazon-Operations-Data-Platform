import React, { useState, useRef, useEffect } from 'react'
import { Button, Input, Space, Typography, Tag, theme } from 'antd'
import { RobotOutlined, SendOutlined, ClearOutlined, LoadingOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import axios from 'axios'

const { Text, Paragraph } = Typography
const { TextArea } = Input

const api = axios.create({ baseURL: '/api', timeout: 60000 })

export default function FloatingAI() {
  const [visible, setVisible] = useState(false)
  const [loading, setLoading] = useState(false)
  const [input, setInput] = useState('')
  const [pos, setPos] = useState({ x: window.innerWidth - 72, y: window.innerHeight - 72 })
  const [panelPos, setPanelPos] = useState(null) // null = auto-position
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef({ startX: 0, startY: 0, startPosX: 0, startPosY: 0 })
  const panelRef = useRef(null)
  const panelDragRef = useRef({ sx: 0, sy: 0, px: 0, py: 0, active: false })
  const [messages, setMessages] = useState([
    { role: 'assistant', text: '你好！我是 LMG 数据平台的 AI 分析助手。可以问我关于利润、费用、产品表现等问题，我会结合当前数据给你分析建议。' }
  ])
  const messagesEnd = useRef(null)
  const { token } = theme.useToken()

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging) return
      e.preventDefault()
      const dx = (e.touches ? e.touches[0].clientX : e.clientX) - dragRef.current.startX
      const dy = (e.touches ? e.touches[0].clientY : e.clientY) - dragRef.current.startY
      const nx = Math.max(0, Math.min(window.innerWidth - 48, dragRef.current.startPosX + dx))
      const ny = Math.max(0, Math.min(window.innerHeight - 48, dragRef.current.startPosY + dy))
      setPos({ x: nx, y: ny })
      // 面板跟随球移动
      if (dragRef.current.panelTop !== undefined) {
        setPanelPos({ x: dragRef.current.panelLeft + dx, y: dragRef.current.panelTop + dy })
      }
    }
    const onEnd = () => setDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onEnd)
    window.addEventListener('touchmove', onMove, { passive: false })
    window.addEventListener('touchend', onEnd)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onEnd)
      window.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onEnd)
    }
  }, [dragging])

  // Panel drag — direct DOM manipulation
  useEffect(() => {
    const onMove = (e) => {
      if (!panelDragRef.current.active) return
      e.preventDefault()
      const dx = e.clientX - panelDragRef.current.sx
      const dy = e.clientY - panelDragRef.current.sy
      const nx = panelDragRef.current.px + dx
      const ny = panelDragRef.current.py + dy
      setPanelPos({ x: nx, y: ny })
    }
    const onEnd = () => { panelDragRef.current.active = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onEnd)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onEnd) }
  }, [])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)

    try {
      // 从 URL 读取当前筛选条件
      const params = new URLSearchParams(window.location.search)
      const body = {
        message: text,
        store: localStorage.getItem('currentStore') || params.get('store') || '',
        country: localStorage.getItem('currentCountry') || params.get('country') || '',
        year: parseInt(params.get('year')) || 2026,
        month: parseInt(params.get('month')) || 5,
      }

      const res = await api.post('/ai/chat', body)
      setMessages(prev => [...prev, { role: 'assistant', text: res.data.reply }])
    } catch (err) {
      const errMsg = err.response?.data?.detail || err.message || 'AI 调用失败'
      setMessages(prev => [...prev, { role: 'assistant', text: '抱歉，请求失败：' + errMsg }])
    } finally {
      setLoading(false)
    }
  }

  const clearMessages = () => {
    setMessages([
      { role: 'assistant', text: '对话已清空。有什么可以帮你的？' }
    ])
  }

  const quickPrompts = [
    '这个月哪些产品亏损最严重？',
    '利润和上月相比怎么样？',
    '广告费占比是否偏高？',
    '有没有优化利润的建议？',
  ]

  return (
    <>
      {/* Floating button — draggable */}
      <div
        onMouseDown={(e) => {
          // 面板跟随：记录面板当前位置
          const panelEl = document.getElementById('ai-panel')
          if (panelEl && visible) {
            const pr = panelEl.getBoundingClientRect()
            dragRef.current = { startX: e.clientX, startY: e.clientY, startPosX: pos.x, startPosY: pos.y, panelLeft: pr.left, panelTop: pr.top }
          } else {
            dragRef.current = { startX: e.clientX, startY: e.clientY, startPosX: pos.x, startPosY: pos.y }
          }
          setDragging(true)
        }}
        onTouchStart={(e) => {
          dragRef.current = { startX: e.touches[0].clientX, startY: e.touches[0].clientY, startPosX: pos.x, startPosY: pos.y }
          setDragging(true)
        }}
        onClick={() => { if (!dragging) setVisible(!visible) }}
        style={{
          position: 'fixed', left: pos.x, top: pos.y, zIndex: 999,
          width: 48, height: 48, borderRadius: 24,
          background: 'linear-gradient(135deg, #1677ff, #0958d9)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: dragging ? 'grabbing' : 'grab',
          boxShadow: '0 4px 12px rgba(22,119,255,0.4)',
          transition: dragging ? 'none' : 'box-shadow 0.2s',
          userSelect: 'none',
        }}
      >
        <RobotOutlined style={{ fontSize: 24, color: '#fff' }} />
      </div>

      {/* Chat panel — opens to left if ball is on right, below if ball is top */}
      {visible && (
        <>
          <div
            onClick={() => setVisible(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 999, background: 'transparent' }}
          />
          <div
            id="ai-panel"
            style={{
              position: 'fixed',
              left: panelPos ? panelPos.x : (pos.x > window.innerWidth / 2 ? Math.max(0, pos.x - 360) : Math.min(pos.x + 56, window.innerWidth - 360)),
              top: panelPos ? panelPos.y : (pos.y > window.innerHeight / 2 ? Math.max(0, pos.y - 480) : pos.y),
              zIndex: 1000,
              width: 360, height: 480, borderRadius: 16,
              background: '#fff', boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
            onMouseDown={e => e.stopPropagation()}
          >
          {/* Header — draggable */}
          <div
            onMouseDown={(e) => {
              const rect = e.currentTarget.parentElement.getBoundingClientRect()
              panelDragRef.current = { sx: e.clientX, sy: e.clientY, px: rect.left, py: rect.top, active: true }
              if (!panelPos) setPanelPos({ x: rect.left, y: rect.top })
            }}
            style={{
              padding: '12px 16px', background: 'linear-gradient(135deg, #1677ff, #0958d9)',
              color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: 'grab', userSelect: 'none',
            }}
          >
            <Space>
              <RobotOutlined />
              <span style={{ fontWeight: 600, fontSize: 14 }}>AI 助手</span>
            </Space>
            <Space size={4}>
              <Button type="text" size="small" icon={<ClearOutlined />} onClick={clearMessages}
                style={{ color: '#fff' }} />
              <Button type="text" size="small" onClick={() => setVisible(false)}
                style={{ color: '#fff', fontSize: 16 }}>✕</Button>
            </Space>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 8, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {m.role === 'assistant' ? (
                  <div style={{
                    maxWidth: '92%', padding: '6px 10px', borderRadius: 12, fontSize: 13,
                    background: '#f5f5f5', color: token.colorText, overflow: 'hidden',
                    wordBreak: 'break-word',
                  }}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        table: ({children}) => <table style={{borderCollapse:'collapse',width:'100%',margin:'4px 0',fontSize:11}}>{children}</table>,
                        th: ({children}) => <th style={{border:'1px solid #ddd',padding:'3px 6px',background:'#e8f0fe',textAlign:'left'}}>{children}</th>,
                        td: ({children}) => <td style={{border:'1px solid #ddd',padding:'2px 5px'}}>{children}</td>,
                        p: ({children}) => <span>{children}<br/></span>,
                        ul: ({children}) => <ul style={{margin:'2px 0',paddingLeft:18}}>{children}</ul>,
                        ol: ({children}) => <ol style={{margin:'2px 0',paddingLeft:18}}>{children}</ol>,
                        li: ({children}) => <li style={{margin:'1px 0'}}>{children}</li>,
                        strong: ({children}) => <strong>{children}</strong>,
                        code: ({children}) => <code style={{background:'#eee',padding:'1px 4px',borderRadius:3}}>{children}</code>,
                        hr: () => <hr style={{margin:'6px 0',border:'none',borderTop:'1px solid #ddd'}}/>,
                        h1: ({children}) => <div style={{fontWeight:700,fontSize:15,margin:'6px 0 2px'}}>{children}</div>,
                        h2: ({children}) => <div style={{fontWeight:700,fontSize:14,margin:'4px 0 2px'}}>{children}</div>,
                        h3: ({children}) => <div style={{fontWeight:600,fontSize:13,margin:'3px 0 2px'}}>{children}</div>,
                      }}
                    >{m.text}</ReactMarkdown>
                  </div>
                ) : (
                  <div style={{
                    maxWidth: '85%', padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.5,
                    background: token.colorPrimary, color: '#fff',
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  }}>
                    {m.text}
                  </div>
                )}
              </div>
            ))}
            {loading && <div style={{ textAlign: 'center' }}><LoadingOutlined style={{ color: token.colorPrimary }} /> 分析中...</div>}
            <div ref={messagesEnd} />
          </div>

          {/* Quick prompts */}
          {messages.length <= 1 && (
            <div style={{ padding: '0 12px 6px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {quickPrompts.map(p => (
                  <Tag key={p} style={{ cursor: 'pointer', fontSize: 11, margin: 0 }} color="blue"
                    onClick={() => { setInput(p); document.getElementById('ai-input')?.focus() }}>{p}</Tag>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div style={{ padding: '8px 12px', borderTop: '1px solid #f0f0f0' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <TextArea id="ai-input" value={input} onChange={e => setInput(e.target.value)}
                onPressEnter={e => { e.preventDefault(); sendMessage() }}
                placeholder="输入问题..." autoSize={{ minRows: 1, maxRows: 2 }}
                disabled={loading} style={{ flex: 1, fontSize: 13 }} />
              <Button type="primary" icon={<SendOutlined />} onClick={sendMessage}
                loading={loading} disabled={!input.trim()} size="small" />
            </div>
          </div>
        </div>
        </>
      )}
    </>
  )
}
