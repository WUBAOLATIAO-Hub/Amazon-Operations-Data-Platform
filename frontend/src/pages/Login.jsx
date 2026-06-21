import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'

const WORD = ['L', 'E', 'M', 'E', 'G', 'A'];

class LetterPhysics {
  constructor(el, targetX, targetY, index, W, H) {
    this.el = el;
    this.tx = targetX;
    this.ty = targetY;
    this.index = index;

    const side = Math.random();
    const m = 100;
    if (side < 0.2)       { this.x = -m - Math.random()*150; this.y = Math.random()*H; }
    else if (side < 0.4)  { this.x = W + m + Math.random()*150; this.y = Math.random()*H; }
    else if (side < 0.6)  { this.x = Math.random()*W; this.y = -m - Math.random()*120; }
    else if (side < 0.8)  { this.x = Math.random()*W; this.y = H + m + Math.random()*120; }
    else                  { this.x = W/2 + (Math.random()-0.5)*W*0.8; this.y = H/2 + (Math.random()-0.5)*H*0.8; }

    const dx = this.tx - this.x;
    const dy = this.ty - this.y;
    const speed = 1.5 + Math.random() * 3;
    const angle = Math.atan2(dy, dx) + (Math.random() - 0.5) * 0.4;
    this.vx = Math.cos(angle) * speed;
    this.vy = Math.sin(angle) * speed;

    this.halfWidth = 30;
    this.locked = false;
  }

  updateMetrics(w) { this.halfWidth = w / 2 + 8; }

  applyForces(others) {
    if (this.locked) return;
    const dx = this.tx - this.x;
    const dy = this.ty - this.y;
    this.vx += dx * 0.012;
    this.vy += dy * 0.012;
    for (const o of others) {
      if (o === this || o.locked) continue;
      if (Math.abs(this.index - o.index) !== 1) continue;
      const rx = this.x - o.x;
      const ry = this.y - o.y;
      const d = Math.hypot(rx, ry);
      const minDist = this.halfWidth + o.halfWidth;
      if (d < minDist && d > 0.01) {
        const overlap = minDist - d;
        const force = overlap * 0.15;
        this.vx += (rx / d) * force;
        this.vy += (ry / d) * force;
      }
    }
    this.vx *= 0.94;
    this.vy *= 0.94;
    const spd = Math.hypot(this.vx, this.vy);
    if (spd > 25) { this.vx = (this.vx/spd)*25; this.vy = (this.vy/spd)*25; }
    const distToTarget = Math.hypot(this.tx - this.x, this.ty - this.y);
    if (distToTarget < 6) {
      this.x = this.tx; this.y = this.ty;
      this.vx = 0; this.vy = 0; this.locked = true;
      this.el.style.left = this.x + 'px';
      this.el.style.top = this.y + 'px';
    }
  }

  update() {
    if (this.locked) return;
    this.x += this.vx; this.y += this.vy;
    this.el.style.left = this.x + 'px';
    this.el.style.top = this.y + 'px';
  }

  isSettled() { return this.locked; }
}

function getLetterMetrics() {
  const probe = document.createElement('div');
  probe.style.cssText = 'position:absolute;visibility:hidden;font-family:"Bebas Neue","Inter","Arial Black",sans-serif;font-weight:400;font-size:clamp(80px,13vw,160px);white-space:nowrap;';
  document.body.appendChild(probe);
  const metrics = [];
  let totalW = 0;
  WORD.forEach(ch => {
    probe.textContent = ch;
    const w = probe.getBoundingClientRect().width;
    metrics.push({ char: ch, width: w });
    totalW += w;
  });
  document.body.removeChild(probe);
  const gap = Math.max(80, Math.min(160, window.innerWidth * 0.13)) * 0.06;
  totalW += gap * (WORD.length - 1);
  return { metrics, totalW, gap };
}

// 独立的CSS样式 — 不依赖@import，用link标签加载字体
const LOGIN_CSS = `
.login-page-root { position:fixed; inset:0; overflow:hidden; background:#fafbfc; font-family:'Inter','Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif; }
.login-page-root *, .login-page-root *::before, .login-page-root *::after { margin:0; padding:0; box-sizing:border-box; }
.login-grid-texture { position:fixed; inset:0; z-index:0; pointer-events:none; background-image:linear-gradient(rgba(0,0,0,0.012) 1px,transparent 1px),linear-gradient(90deg,rgba(0,0,0,0.012) 1px,transparent 1px); background-size:40px 40px; }
.login-letter-stage { position:fixed; inset:0; z-index:10; pointer-events:none; transition:transform 1.5s cubic-bezier(0.32,0.72,0,1); }
.login-letter-stage.shifted { transform:translateX(-20%); }
.login-letter { position:absolute; font-family:'Bebas Neue','Inter','Arial Black',sans-serif; font-weight:400; font-size:clamp(80px,13vw,160px); color:#1a1d28; line-height:1; transform:translate(-50%,-50%); will-change:left,top; }
.login-logo-section { position:fixed; inset:0; z-index:9; display:flex; align-items:center; justify-content:center; pointer-events:none; opacity:0; transition:opacity 0.6s ease; }
.login-logo-section.visible { opacity:1; }
.login-logo-section.shifted { transform:translateX(-20%); transition:all 1.2s cubic-bezier(0.32,0.72,0,1); }
.login-logo-main { font-family:'Bebas Neue','Inter',sans-serif; font-weight:400; font-size:clamp(64px,8vw,120px); letter-spacing:0.06em; color:#1a1d28; line-height:1; position:relative; display:inline-block; }
.login-logo-main::after { content:''; position:absolute; bottom:-4px; left:0; right:0; height:4px; background:#2563eb; border-radius:2px; transform:scaleX(0); transform-origin:left; transition:transform 0.8s cubic-bezier(0.32,0.72,0,1) 0.4s; }
.login-logo-section.shifted .login-logo-main::after { transform:scaleX(1); }
.login-logo-subtitle { font-family:'Noto Sans SC',sans-serif; font-size:clamp(13px,1.5vw,16px); font-weight:400; color:#6b7280; margin-top:0.8em; letter-spacing:0.12em; }
.login-logo-desc { font-family:'Noto Sans SC',sans-serif; font-size:0.75rem; color:#6b7280; opacity:0.5; margin-top:0.5em; letter-spacing:0.06em; }
.login-card-section { position:fixed; left:56%; top:50%; transform:translate(80px,-50%); z-index:10; opacity:0; pointer-events:none; transition:all 0.55s cubic-bezier(0.22,0.61,0.36,1); }
.login-card-section.visible { opacity:1; transform:translate(0,-50%); pointer-events:all; }
.login-card-box { background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:2.8rem 2.5rem 2.4rem; width:min(440px,88vw); box-shadow:0 4px 24px rgba(0,0,0,0.06),0 1px 4px rgba(0,0,0,0.04); }
.login-card-header { text-align:center; margin-bottom:1.8rem; }
.login-card-header h2 { font-family:'Noto Sans SC',sans-serif; font-weight:600; font-size:1.3rem; color:#1a1d28; letter-spacing:0.06em; }
.login-card-sep { width:36px; height:3px; background:#2563eb; border-radius:2px; margin:12px auto 0; }
.login-form-group { margin-bottom:1.3rem; }
.login-form-group label { display:block; font-size:0.85rem; font-weight:500; color:#1a1d28; margin-bottom:0.4rem; letter-spacing:0.04em; }
.login-input-wrap { position:relative; }
.login-input-wrap .login-icon { position:absolute; left:15px; top:50%; transform:translateY(-50%); width:19px; height:19px; pointer-events:none; opacity:0.35; }
.login-input-wrap input { width:100%; padding:0.8rem 1.2rem 0.8rem 48px; background:#f9fafb; border:1.5px solid #e5e7eb; border-radius:10px; color:#1a1d28; font-family:'Inter','Noto Sans SC',sans-serif; font-size:0.95rem; letter-spacing:0.03em; outline:none; transition:all 0.3s ease; }
.login-input-wrap input::placeholder { color:#c4c8d0; font-size:0.88rem; }
.login-input-wrap input:focus { border-color:#93c5fd; background:#fff; box-shadow:0 0 0 3px rgba(37,99,235,0.08); }
.login-input-wrap input:focus ~ .login-icon { opacity:0.7; }
.login-btn { width:100%; margin-top:0.6rem; padding:0.9rem; background:#2563eb; border:none; border-radius:10px; color:#fff; font-family:'Noto Sans SC',sans-serif; font-weight:500; font-size:1.05rem; letter-spacing:0.1em; cursor:pointer; transition:all 0.3s ease; }
.login-btn:hover { background:#3b82f6; box-shadow:0 4px 16px rgba(37,99,235,0.25); transform:translateY(-1px); }
.login-btn:active { transform:translateY(0); transition:all 0.06s ease; }
.login-btn:disabled { opacity:0.7; cursor:not-allowed; }
.login-card-meta { margin-top:1rem; text-align:center; font-size:0.68rem; color:#6b7280; opacity:0.45; }
.login-error { margin-top:0.8rem; text-align:center; font-size:0.8rem; color:#ef4444; min-height:1.2em; }
@media (max-width:768px) {
  .login-letter-stage.shifted { transform:translateY(-22%) translateX(0); }
  .login-logo-section.shifted { transform:translateY(-22%); }
  .login-card-section { left:50%; top:60%; transform:translate(-50%,30px); }
  .login-card-section.visible { transform:translate(-50%,0); }
}
`;

export default function Login() {
  const { login } = useAuth();
  const stageRef = useRef(null);
  const cardRef = useRef(null);
  const [animPhase, setAnimPhase] = useState('letters');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const animRef = useRef({ physLetters: [], animId: null, frame: 0, uiTriggered: false });

  const startAnimation = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const letters = stage.querySelectorAll('.login-letter');
    if (!letters.length) return;
    const letterArr = Array.from(letters);
    const W = window.innerWidth;
    const H = window.innerHeight;

    const { metrics, totalW, gap } = getLetterMetrics();
    const startX = W / 2 - totalW / 2;
    const centerY = H / 2;

    letterArr.forEach(l => { l.style.opacity = '0'; l.style.transition = 'none'; });

    const physLetters = [];
    let cursorX = startX;
    WORD.forEach((ch, i) => {
      const el = letterArr[i];
      if (!el) return;
      const lp = new LetterPhysics(el, cursorX + metrics[i].width / 2, centerY, i, W, H);
      lp.updateMetrics(metrics[i].width);
      el.style.left = lp.x + 'px';
      el.style.top = lp.y + 'px';
      cursorX += metrics[i].width + gap;
      physLetters.push(lp);
    });

    const st = animRef.current;
    if (st.animId) cancelAnimationFrame(st.animId);
    st.physLetters = physLetters;
    st.frame = 0;
    st.uiTriggered = false;

    setTimeout(() => {
      letterArr.forEach(l => {
        l.style.opacity = '1';
        l.style.transition = 'opacity 0.2s ease';
      });

      function animate() {
        st.animId = requestAnimationFrame(animate);
        st.frame++;
        let settledCount = 0;
        st.physLetters.forEach(lp => {
          lp.applyForces(st.physLetters);
          lp.update();
          if (lp.isSettled()) settledCount++;
        });
        const settledRatio = st.physLetters.length > 0 ? settledCount / st.physLetters.length : 0;
        const shouldTrigger = !st.uiTriggered && ((settledRatio >= 1 && st.frame > 15) || st.frame > 400);
        if (shouldTrigger) {
          st.uiTriggered = true;
          cancelAnimationFrame(st.animId);
          letterArr.forEach(l => {
            l.style.transition = 'opacity 0.35s ease';
            l.style.opacity = '0';
          });
          setTimeout(() => setAnimPhase('logo'), 200);
          setTimeout(() => setAnimPhase('card'), 800);
        }
      }
      st.animId = requestAnimationFrame(animate);
    }, 200);
  }, []);

  useEffect(() => {
    // 加载Google字体
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Noto+Sans+SC:wght@300;400;500;600&family=Inter:wght@400;500;600&display=swap';
    document.head.appendChild(link);

    // 注入CSS
    const style = document.createElement('style');
    style.textContent = LOGIN_CSS;
    document.head.appendChild(style);

    // 等字体加载后再启动动画
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => startAnimation());
    } else {
      setTimeout(startAnimation, 500);
    }

    const handleResize = () => {
      setAnimPhase('letters');
      setTimeout(startAnimation, 100);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      const st = animRef.current;
      if (st.animId) cancelAnimationFrame(st.animId);
      window.removeEventListener('resize', handleResize);
      if (link.parentNode) link.parentNode.removeChild(link);
      if (style.parentNode) style.parentNode.removeChild(style);
    };
  }, [startAnimation]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const form = e.target;
    const u = form.username.value.trim();
    const p = form.password.value.trim();
    if (!u || !p) { shakeCard(); return; }
    setLoading(true);
    try {
      await login(u, p);
    } catch (err) {
      setError(err.response?.data?.detail || '登录失败');
      shakeCard();
    } finally {
      setLoading(false);
    }
  };

  const shakeCard = () => {
    const card = cardRef.current;
    if (!card) return;
    card.style.transition = 'transform 0.07s ease';
    [-4,4,-3,3,-1,0].forEach((x,i) => setTimeout(() => card.style.transform=`translateX(${x}px)`, i*50));
    setTimeout(() => { card.style.transition = ''; card.style.transform = ''; }, 350);
  };

  const stageShifted = animPhase === 'card';
  const logoVisible = animPhase === 'logo' || animPhase === 'card';

  return (
    <div className="login-page-root">
      <div className="login-grid-texture" />
      <div ref={stageRef} className={`login-letter-stage ${stageShifted ? 'shifted' : ''}`}>
        {WORD.map((ch, i) => (
          <div key={i} className="login-letter">{ch}</div>
        ))}
      </div>
      <div className={`login-logo-section ${logoVisible ? 'visible' : ''} ${stageShifted ? 'shifted' : ''}`}>
        <div style={{ textAlign: 'center' }}>
          <div className="login-logo-main">LEMEGA</div>
          <div className="login-logo-subtitle">亚马逊运营数据智能平台</div>
          <div className="login-logo-desc">多店铺 · 多国家 · 实时利润 · 一站式管理</div>
        </div>
      </div>
      <div ref={cardRef} className={`login-card-section ${stageShifted ? 'visible' : ''}`}>
        <div className="login-card-box">
          <div className="login-card-header">
            <h2>登入控制台</h2>
            <div className="login-card-sep" />
          </div>
          <form onSubmit={handleSubmit} autoComplete="off">
            <div className="login-form-group">
              <label>用户名</label>
              <div className="login-input-wrap">
                <svg className="login-icon" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.8">
                  <circle cx="12" cy="8" r="4"/><path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                </svg>
                <input type="text" name="username" placeholder="请输入用户名" autoComplete="off" spellCheck="false" />
              </div>
            </div>
            <div className="login-form-group">
              <label>密码</label>
              <div className="login-input-wrap">
                <svg className="login-icon" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.8">
                  <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/><circle cx="12" cy="16" r="1"/>
                </svg>
                <input type="password" name="password" placeholder="请输入密码" autoComplete="off" />
              </div>
            </div>
            <button type="submit" className="login-btn" disabled={loading}>
              {loading ? '验证中…' : '登 入'}
            </button>
          </form>
          {error && <div className="login-error">{error}</div>}
          <div className="login-card-meta">LEMEGA · Amazon Operations Intelligence v5.3</div>
        </div>
      </div>
    </div>
  );
}
