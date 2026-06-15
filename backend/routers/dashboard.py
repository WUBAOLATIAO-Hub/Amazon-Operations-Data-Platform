from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, String
from database import get_db
from models import MonthlySummary, DimCountry, DimTime, DimProduct, DimStore

router = APIRouter()


@router.get("/summary")
def get_summary(
    country: str = Query(None, description="国家代码，如 US/UK/DE"),
    store: str = Query(None, description="店铺代码"),
    year: int = Query(None, description="年份"),
    month: int = Query(None, description="月份"),
    db: Session = Depends(get_db),
):
    try:
        # 基础查询
        q = db.query(
            func.sum(MonthlySummary.net_profit_rmb).label("total_net_profit_rmb"),
            func.sum(MonthlySummary.product_sales_rmb).label("total_product_sales_rmb"),
            func.sum(MonthlySummary.order_count).label("total_order_count"),
            func.sum(MonthlySummary.order_qty).label("total_order_qty"),
            # 加权平均利润率 = 总利润 / 总销售额
            func.coalesce(
                func.sum(MonthlySummary.net_profit_rmb) / func.nullif(func.sum(MonthlySummary.product_sales_rmb), 0),
                0
            ).label("avg_net_profit_rate"),
            # 广告指标（花费按每行汇率转RMB）
            func.sum(MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate).label("total_ad_spend_rmb"),
            func.sum(MonthlySummary.ad_sales_usd * MonthlySummary.exchange_rate).label("total_ad_sales_rmb"),
            func.sum(MonthlySummary.impressions).label("total_impressions"),
            func.sum(MonthlySummary.clicks).label("total_clicks"),
            func.sum(MonthlySummary.ad_orders).label("total_ad_orders"),
        )

        # 关联筛选
        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                DimCountry.code == country.upper()
            )
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(
                DimStore.code == store
            )
        if year or month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
            if year:
                q = q.filter(DimTime.time_year == year)
            if month:
                q = q.filter(DimTime.time_month == month)

        row = q.one()

        # 计算广告指标
        ad_spend = float(row.total_ad_spend_rmb or 0)
        ad_sales = float(row.total_ad_sales_rmb or 0)
        impressions = int(row.total_impressions or 0)
        clicks = int(row.total_clicks or 0)
        ad_orders = int(row.total_ad_orders or 0)

        acos = (ad_spend / ad_sales * 100) if ad_sales > 0 else 0
        roas = (ad_sales / ad_spend) if ad_spend > 0 else 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        cpc = (ad_spend / clicks) if clicks > 0 else 0
        cvr = (ad_orders / clicks * 100) if clicks > 0 else 0

        current = {
            "total_net_profit_rmb": float(row.total_net_profit_rmb or 0),
            "total_product_sales_rmb": float(row.total_product_sales_rmb or 0),
            "total_order_count": int(row.total_order_count or 0),
            "total_order_qty": int(row.total_order_qty or 0),
            "avg_net_profit_rate": float(row.avg_net_profit_rate or 0),
            # 广告
            "total_ad_spend_rmb": ad_spend,
            "acos": round(acos, 2),
            "roas": round(roas, 2),
            "ctr": round(ctr, 2),
            "cpc": round(cpc, 2),
            "cvr": round(cvr, 2),
            "total_impressions": impressions,
            "total_clicks": clicks,
        }

        # 环比：上个月 / 上个年（统一用加权平均）
        prev = None
        if year and month:
            prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
            pq = db.query(
                func.sum(MonthlySummary.net_profit_rmb).label("total_net_profit_rmb"),
                func.sum(MonthlySummary.product_sales_rmb).label("total_product_sales_rmb"),
                func.sum(MonthlySummary.order_count).label("total_order_count"),
                func.coalesce(
                    func.sum(MonthlySummary.net_profit_rmb) / func.nullif(func.sum(MonthlySummary.product_sales_rmb), 0),
                    0
                ).label("avg_net_profit_rate"),
                func.sum(MonthlySummary.ad_spend_usd).label("total_ad_spend_usd"),
                func.sum(MonthlySummary.ad_sales_usd).label("total_ad_sales_usd"),
            )
            if country:
                pq = pq.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                    DimCountry.code == country.upper()
                )
            if store:
                pq = pq.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)
            pq = pq.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(
                DimTime.time_year == prev_year, DimTime.time_month == prev_month
            )
            prow = pq.one()
            prev_ad_spend = float(prow.total_ad_spend_usd or 0)
            prev_ad_sales = float(prow.total_ad_sales_usd or 0)
            prev = {
                "total_net_profit_rmb": float(prow.total_net_profit_rmb or 0),
                "total_product_sales_rmb": float(prow.total_product_sales_rmb or 0),
                "total_order_count": int(prow.total_order_count or 0),
                "avg_net_profit_rate": float(prow.avg_net_profit_rate or 0),
                "acos": round((prev_ad_spend / prev_ad_sales * 100) if prev_ad_sales > 0 else 0, 2),
                "roas": round((prev_ad_sales / prev_ad_spend) if prev_ad_spend > 0 else 0, 2),
            }
        elif year and not month:
            prev_year = year - 1
            pq = db.query(
                func.sum(MonthlySummary.net_profit_rmb).label("total_net_profit_rmb"),
                func.sum(MonthlySummary.product_sales_rmb).label("total_product_sales_rmb"),
                func.sum(MonthlySummary.order_count).label("total_order_count"),
                func.coalesce(
                    func.sum(MonthlySummary.net_profit_rmb) / func.nullif(func.sum(MonthlySummary.product_sales_rmb), 0),
                    0
                ).label("avg_net_profit_rate"),
                func.sum(MonthlySummary.ad_spend_usd).label("total_ad_spend_usd"),
                func.sum(MonthlySummary.ad_sales_usd).label("total_ad_sales_usd"),
            )
            if country:
                pq = pq.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                    DimCountry.code == country.upper()
                )
            if store:
                pq = pq.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)
            pq = pq.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(DimTime.time_year == prev_year)
            prow = pq.one()
            prev_ad_spend = float(prow.total_ad_spend_usd or 0)
            prev_ad_sales = float(prow.total_ad_sales_usd or 0)
            prev = {
                "total_net_profit_rmb": float(prow.total_net_profit_rmb or 0),
                "total_product_sales_rmb": float(prow.total_product_sales_rmb or 0),
                "total_order_count": int(prow.total_order_count or 0),
                "avg_net_profit_rate": float(prow.avg_net_profit_rate or 0),
                "acos": round((prev_ad_spend / prev_ad_sales * 100) if prev_ad_sales > 0 else 0, 2),
                "roas": round((prev_ad_sales / prev_ad_spend) if prev_ad_spend > 0 else 0, 2),
            }

        # 计算环比变化
        change = None
        if prev:
            change = {}
            for key in ["total_net_profit_rmb", "total_product_sales_rmb", "total_order_count", "avg_net_profit_rate", "acos", "roas"]:
                curr_val = current.get(key, 0)
                prev_val = prev.get(key, 0)
                if prev_val != 0:
                    change[key] = round((curr_val - prev_val) / abs(prev_val) * 100, 2)
                else:
                    change[key] = None

        return {"current": current, "previous": prev, "change_percent": change}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
def get_trend(
    country: str = Query(None, description="国家代码"),
    store: str = Query(None, description="店铺代码"),
    dimension: str = Query("month", description="聚合维度: month/year"),
    db: Session = Depends(get_db),
):
    try:
        if dimension == "year":
            label_expr = func.cast(DimTime.time_year, String).label("label")
            group_expr = DimTime.time_year
        else:
            label_expr = DimTime.year_month.label("label")
            group_expr = (DimTime.time_year, DimTime.time_month)

        q = db.query(
            label_expr,
            func.sum(MonthlySummary.net_profit_rmb).label("net_profit"),
            func.sum(MonthlySummary.product_sales_rmb).label("sales"),
            func.sum(MonthlySummary.order_count).label("orders"),
        ).join(DimTime, MonthlySummary.time_id == DimTime.id)

        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                DimCountry.code == country.upper()
            )
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(
                DimStore.code == store
            )

        if dimension == "year":
            q = q.group_by(DimTime.time_year).order_by(DimTime.time_year)
        else:
            q = q.group_by(DimTime.year_month, DimTime.time_year, DimTime.time_month).order_by(DimTime.time_year, DimTime.time_month)

        rows = q.all()

        data = [
            {
                "label": row.label,
                "net_profit": float(row.net_profit or 0),
                "sales": float(row.sales or 0),
                "orders": int(row.orders or 0),
            }
            for row in rows
        ]

        return {"data": data, "dimension": dimension}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost-breakdown")
def get_cost_breakdown(
    country: str = Query(None, description="国家代码"),
    store: str = Query(None, description="店铺代码"),
    year: int = Query(None, description="年份"),
    month: int = Query(None, description="月份"),
    db: Session = Depends(get_db),
):
    """费用拆分数据（用于瀑布图）"""
    try:
        # USD 字段按每行汇率换算为 RMB（commission/fba/ad 等存的是当地货币，exchange_rate 是当地→RMB）
        q = db.query(
            func.sum(MonthlySummary.product_sales_rmb).label("sales"),
            func.sum(MonthlySummary.net_profit_rmb).label("net_profit"),
            func.sum(MonthlySummary.product_cost_rmb).label("product_cost"),
            func.sum(MonthlySummary.freight_cost_rmb).label("freight"),
            func.sum(MonthlySummary.commission_usd * MonthlySummary.exchange_rate).label("commission_rmb"),
            func.sum(MonthlySummary.fba_fee_usd * MonthlySummary.exchange_rate).label("fba_rmb"),
            func.sum(MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate).label("ad_rmb"),
            func.sum(MonthlySummary.storage_fee_usd * MonthlySummary.exchange_rate).label("storage_rmb"),
            func.sum(MonthlySummary.returns_fee_usd * MonthlySummary.exchange_rate).label("returns_rmb"),
            func.sum(MonthlySummary.inbound_fee_usd * MonthlySummary.exchange_rate).label("inbound_rmb"),
            func.sum(MonthlySummary.promo_rebate_usd * MonthlySummary.exchange_rate).label("promo_rmb"),
            func.sum(MonthlySummary.adjustment_usd * MonthlySummary.exchange_rate).label("adjustment_rmb"),
        )

        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(DimCountry.code == country.upper())
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)
        if year or month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
            if year:
                q = q.filter(DimTime.time_year == year)
            if month:
                q = q.filter(DimTime.time_month == month)

        row = q.one()

        sales = float(row.sales or 0)
        net_profit = float(row.net_profit or 0)
        product_cost = abs(float(row.product_cost or 0))
        freight = abs(float(row.freight or 0))
        commission = abs(float(row.commission_rmb or 0))
        fba_fee = abs(float(row.fba_rmb or 0))
        ad_spend = abs(float(row.ad_rmb or 0))
        storage = abs(float(row.storage_rmb or 0))
        returns = abs(float(row.returns_rmb or 0))
        inbound = abs(float(row.inbound_rmb or 0))
        promo = abs(float(row.promo_rmb or 0))
        adjustment = float(row.adjustment_rmb or 0)

        # 费用项（正数表示"支出"）
        expenses = [
            {"name": "采购成本", "value": round(product_cost, 2)},
            {"name": "亚马逊佣金", "value": round(commission, 2)},
            {"name": "FBA配送费", "value": round(fba_fee, 2)},
            {"name": "广告费", "value": round(ad_spend, 2)},
            {"name": "头程运费", "value": round(freight, 2)},
            {"name": "仓储费", "value": round(storage, 2)},
            {"name": "入库费", "value": round(inbound, 2)},
            {"name": "退货费", "value": round(returns, 2)},
            {"name": "促销扣减", "value": round(promo, 2)},
        ]

        # 差额：净利润(实际) vs 销售额-费用(重算) 的差值（四舍五入误差等）
        total_expense = sum(e["value"] for e in expenses)
        calc_profit = sales - total_expense + adjustment
        diff = net_profit - calc_profit

        return {
            "sales": round(sales, 2),
            "expenses": expenses,
            "adjustment": round(adjustment, 2),
            "net_profit": round(net_profit, 2),
            "diff": round(diff, 2),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-distribution")
def get_product_distribution(
    country: str = Query(None, description="国家代码"),
    store: str = Query(None, description="店铺代码"),
    year: int = Query(None, description="年份"),
    month: int = Query(None, description="月份"),
    db: Session = Depends(get_db),
):
    """获取产品销售分布数据（用于饼图和柱状图）"""
    try:
        q = (
            db.query(
                DimProduct.product_name,
                DimProduct.color,
                func.sum(MonthlySummary.order_count).label("order_count"),
                func.sum(MonthlySummary.product_sales_rmb).label("sales_rmb"),
                func.sum(MonthlySummary.net_profit_rmb).label("net_profit"),
            )
            .join(DimProduct, MonthlySummary.product_id == DimProduct.id)
            .join(DimCountry, MonthlySummary.country_id == DimCountry.id)
        )

        if country:
            q = q.filter(DimCountry.code == country.upper())
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)
        if year or month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
            if year:
                q = q.filter(DimTime.time_year == year)
            if month:
                q = q.filter(DimTime.time_month == month)

        q = q.group_by(DimProduct.product_name, DimProduct.color).order_by(func.sum(MonthlySummary.product_sales_rmb).desc())
        rows = q.all()

        data = []
        for row in rows:
            pname = row.product_name or "未知产品"
            name = f"{pname} ({row.color})" if row.color else pname
            data.append({
                "name": name,
                "product_name": row.product_name,
                "color": row.color,
                "order_count": int(row.order_count or 0),
                "sales_rmb": float(row.sales_rmb or 0),
                "net_profit": float(row.net_profit or 0),
            })

        return {"data": data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
