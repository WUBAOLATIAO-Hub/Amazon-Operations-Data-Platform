"""
AI 分析助手 — 对话接口
自动注入当前平台数据作为上下文
"""
import os, httpx
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import MonthlySummary, DimCountry, DimStore, DimTime, DimProduct

router = APIRouter()

AI_API_KEY = os.getenv("AI_API_KEY", "sk-776661ea24c9471eb28a8ba8088b2160")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/anthropic")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # openai 或 anthropic

SYSTEM_PROMPT = """你是 LMG 跨境电商数据平台的 AI 分析助手。

你的职责：
1. 分析利润数据，找出盈亏原因
2. 解读费用结构，定位成本异常
3. 对比店铺/国家/产品表现，给出优化建议
4. 回答数据计算逻辑（如利润公式、费用组成）

回答要求：
- 简洁专业，用中文
- 引用具体数字时标注单位
- 涉及公式时给出计算过程
- 不知道的数据直接说不知道，不要编造
"""


def _build_context(db: Session, store: str, country: str, year: int, month: int) -> str:
    """根据筛选条件构建数据上下文"""
    parts = []

    # 店铺信息
    if store:
        parts.append(f"当前店铺：{store}")
    if country:
        parts.append(f"当前国家：{country}")
    if year or month:
        period = f"{year or '全部'}年"
        if month:
            period += f"{month}月"
        parts.append(f"当前期间：{period}")

    # 查询汇总数据
    store_id = None
    country_id = None
    if store:
        s = db.query(DimStore).filter(DimStore.code == store).first()
        if s:
            store_id = s.id
    if country:
        c = db.query(DimCountry).filter(DimCountry.code == country.upper()).first()
        if c:
            country_id = c.id

    q = db.query(
        func.sum(MonthlySummary.product_sales_rmb).label("sales"),
        func.sum(MonthlySummary.net_profit_rmb).label("profit"),
        func.sum(MonthlySummary.order_count).label("orders"),
        func.sum(MonthlySummary.product_cost_rmb).label("cost"),
        func.sum(MonthlySummary.freight_cost_rmb).label("freight"),
        func.sum(MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate).label("ad"),
        func.sum(MonthlySummary.storage_fee_usd * MonthlySummary.exchange_rate).label("storage"),
        func.sum(MonthlySummary.commission_usd * MonthlySummary.exchange_rate).label("commission"),
        func.sum(MonthlySummary.fba_fee_usd * MonthlySummary.exchange_rate).label("fba"),
    )
    if store_id:
        q = q.filter(MonthlySummary.store_id == store_id)
    if country_id:
        q = q.filter(MonthlySummary.country_id == country_id)
    if year or month:
        q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
        if year:
            q = q.filter(DimTime.time_year == year)
        if month:
            q = q.filter(DimTime.time_month == month)

    row = q.one()
    sales = float(row.sales or 0)
    profit = float(row.profit or 0)
    orders = int(row.orders or 0)
    rate = round(profit / sales * 100, 1) if sales else 0

    parts.append(f"\n汇总数据：")
    parts.append(f"- 销售额：¥{sales:,.2f}")
    parts.append(f"- 净利润：¥{profit:,.2f}（利润率 {rate}%）")
    parts.append(f"- 订单数：{orders}")
    parts.append(f"- 采购成本：¥{float(row.cost or 0):,.2f}")
    parts.append(f"- 头程运费：¥{float(row.freight or 0):,.2f}")
    parts.append(f"- 广告费：¥{float(row.ad or 0):,.2f}")
    parts.append(f"- 仓储费：¥{float(row.storage or 0):,.2f}")
    parts.append(f"- 佣金：¥{float(row.commission or 0):,.2f}")
    parts.append(f"- FBA费：¥{float(row.fba or 0):,.2f}")

    # 利润 Top 3 和 Bottom 3
    top_q = db.query(
        DimProduct.sku, DimProduct.product_name,
        MonthlySummary.net_profit_rmb, MonthlySummary.product_sales_rmb,
    ).join(DimProduct, MonthlySummary.product_id == DimProduct.id)
    if store_id:
        top_q = top_q.filter(MonthlySummary.store_id == store_id)
    if country_id:
        top_q = top_q.filter(MonthlySummary.country_id == country_id)
    if year or month:
        top_q = top_q.join(DimTime, MonthlySummary.time_id == DimTime.id)
        if year:
            top_q = top_q.filter(DimTime.time_year == year)
        if month:
            top_q = top_q.filter(DimTime.time_month == month)
    top_q = top_q.filter(MonthlySummary.order_count > 0)

    top3 = top_q.order_by(MonthlySummary.net_profit_rmb.desc()).limit(3).all()
    bottom3 = top_q.order_by(MonthlySummary.net_profit_rmb.asc()).limit(3).all()

    if top3:
        parts.append(f"\n利润最高 TOP3：")
        for r in top3:
            parts.append(f"  {r.sku}（{r.product_name}）：¥{float(r.net_profit_rmb):,.2f}")
    if bottom3:
        parts.append(f"\n亏损最深 TOP3：")
        for r in bottom3:
            parts.append(f"  {r.sku}（{r.product_name}）：¥{float(r.net_profit_rmb):,.2f}")

    return "\n".join(parts)


@router.post("/chat")
async def ai_chat(
    message: str = Body(..., description="用户消息"),
    store: str = Body(None),
    country: str = Body(None),
    year: int = Body(None),
    month: int = Body(None),
    db: Session = Depends(get_db),
):
    """AI 对话接口"""
    if not AI_API_KEY:
        return {"reply": "AI 助手未配置 API Key，请在 .env 中设置 AI_API_KEY 和 AI_BASE_URL"}

    try:
        context = _build_context(db, store, country, year, month)
        system = SYSTEM_PROMPT + "\n\n当前平台数据：\n" + context

        async with httpx.AsyncClient(timeout=60) as client:
            if AI_PROVIDER == "anthropic":
                resp = await client.post(
                    f"{AI_BASE_URL}/v1/messages",
                    headers={
                        "x-api-key": AI_API_KEY,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": AI_MODEL,
                        "max_tokens": 4000,
                        "system": system,
                        "messages": [{"role": "user", "content": message}],
                    },
                )
                data = resp.json()
                reply = data.get("content", [{}])[0].get("text", "AI 返回为空")
            else:
                resp = await client.post(
                    f"{AI_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": AI_MODEL,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": message},
                        ],
                        "max_tokens": 4000,
                        "temperature": 0.7,
                    },
                )
                data = resp.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "AI 返回为空")
            return {"reply": reply}

    except Exception as e:
        return {"reply": f"AI 调用失败：{str(e)}"}
