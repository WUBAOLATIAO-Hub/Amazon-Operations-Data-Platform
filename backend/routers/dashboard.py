from fastapi import APIRouter, Depends, Query
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
            # 加权平均利润率 = 总利润 / 总销售额（前端再×100转为百分比）
            func.coalesce(
                func.sum(MonthlySummary.net_profit_rmb) / func.nullif(func.sum(MonthlySummary.product_sales_rmb), 0),
                0
            ).label("avg_net_profit_rate"),
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

        current = {
            "total_net_profit_rmb": float(row.total_net_profit_rmb or 0),
            "total_product_sales_rmb": float(row.total_product_sales_rmb or 0),
            "total_order_count": int(row.total_order_count or 0),
            "avg_net_profit_rate": float(row.avg_net_profit_rate or 0),
        }

        # 环比：上个月 / 上个年
        prev = None
        if year and month:
            # 上个月
            prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
            pq = db.query(
                func.sum(MonthlySummary.net_profit_rmb).label("total_net_profit_rmb"),
                func.sum(MonthlySummary.product_sales_rmb).label("total_product_sales_rmb"),
                func.sum(MonthlySummary.order_count).label("total_order_count"),
                func.avg(MonthlySummary.net_profit_rate).label("avg_net_profit_rate"),
            )
            if country:
                pq = pq.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                    DimCountry.code == country.upper()
                )
            pq = pq.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(
                DimTime.time_year == prev_year, DimTime.time_month == prev_month
            )
            prow = pq.one()
            prev = {
                "total_net_profit_rmb": float(prow.total_net_profit_rmb or 0),
                "total_product_sales_rmb": float(prow.total_product_sales_rmb or 0),
                "total_order_count": int(prow.total_order_count or 0),
                "avg_net_profit_rate": float(prow.avg_net_profit_rate or 0),
            }
        elif year and not month:
            # 上个年
            prev_year = year - 1
            pq = db.query(
                func.sum(MonthlySummary.net_profit_rmb).label("total_net_profit_rmb"),
                func.sum(MonthlySummary.product_sales_rmb).label("total_product_sales_rmb"),
                func.sum(MonthlySummary.order_count).label("total_order_count"),
                func.avg(MonthlySummary.net_profit_rate).label("avg_net_profit_rate"),
            )
            if country:
                pq = pq.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                    DimCountry.code == country.upper()
                )
            pq = pq.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(DimTime.time_year == prev_year)
            prow = pq.one()
            prev = {
                "total_net_profit_rmb": float(prow.total_net_profit_rmb or 0),
                "total_product_sales_rmb": float(prow.total_product_sales_rmb or 0),
                "total_order_count": int(prow.total_order_count or 0),
                "avg_net_profit_rate": float(prow.avg_net_profit_rate or 0),
            }

        # 计算环比变化
        change = None
        if prev:
            change = {}
            for key in current:
                curr_val = current[key]
                prev_val = prev[key]
                if prev_val != 0:
                    change[key] = round((curr_val - prev_val) / abs(prev_val) * 100, 2)
                else:
                    change[key] = None

        return {"current": current, "previous": prev, "change_percent": change}

    except Exception as e:
        return {"detail": str(e)}


@router.get("/trend")
def get_trend(
    country: str = Query(None, description="国家代码"),
    dimension: str = Query("month", description="聚合维度: month/year"),
    db: Session = Depends(get_db),
):
    try:
        if dimension == "year":
            label_expr = func.cast(DimTime.time_year, String).label("label")
            group_expr = DimTime.time_year
            order_expr = DimTime.time_year
        else:
            label_expr = DimTime.year_month.label("label")
            group_expr = (DimTime.time_year, DimTime.time_month)
            order_expr = (DimTime.time_year, DimTime.time_month)

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
        return {"detail": str(e)}


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
            name = f"{row.product_name} ({row.color})" if row.color else row.product_name
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
        return {"detail": str(e)}
