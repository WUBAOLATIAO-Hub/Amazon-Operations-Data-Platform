from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String
from database import get_db
from models import MonthlySummary, DimCountry, DimTime, DimProduct, DimStore

router = APIRouter()


@router.get("/summary")
def get_ad_summary(
    country: str = Query(None, description="国家代码"),
    store: str = Query(None, description="店铺代码"),
    year: int = Query(None, description="年份"),
    month: int = Query(None, description="月份"),
    db: Session = Depends(get_db),
):
    try:
        # 与数据看板一致：广告花费/销售额按每行汇率转RMB
        q = db.query(
            func.sum(MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate).label("total_ad_spend_rmb"),
            func.sum(MonthlySummary.ad_sales_usd * MonthlySummary.exchange_rate).label("total_ad_sales_rmb"),
        )

        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                DimCountry.code == country.upper()
            )
        if year or month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
            if year:
                q = q.filter(DimTime.time_year == year)
            if month:
                q = q.filter(DimTime.time_month == month)
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)

        row = q.one()

        total_spend = float(row.total_ad_spend_rmb or 0)
        total_sales = float(row.total_ad_sales_rmb or 0)

        # ACOS = 广告花费 / 广告销售额 × 100，ROAS = 广告销售额 / 广告花费
        avg_acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        avg_roas = (total_sales / total_spend) if total_spend > 0 else 0

        return {
            "total_ad_spend": round(total_spend, 2),
            "avg_acos": round(avg_acos, 2),
            "avg_roas": round(avg_roas, 2),
        }

    except Exception as e:
        return {"detail": str(e)}


@router.get("/detail")
def get_ad_detail(
    country: str = Query(None, description="国家代码"),
    store: str = Query(None, description="店铺代码"),
    year: int = Query(None, description="年份"),
    month: int = Query(None, description="月份"),
    sort_by: str = Query("ad_spend", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(
            DimProduct.product_name,
            DimProduct.asin,
            (MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate).label("ad_spend_rmb"),
            (MonthlySummary.ad_sales_usd * MonthlySummary.exchange_rate).label("ad_sales_rmb"),
            MonthlySummary.acos,
            MonthlySummary.roas,
            MonthlySummary.ctr,
            MonthlySummary.cpc,
            MonthlySummary.impressions,
            MonthlySummary.clicks,
            MonthlySummary.ad_orders,
            MonthlySummary.conversion_rate,
        ).join(DimProduct, MonthlySummary.product_id == DimProduct.id)

        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                DimCountry.code == country.upper()
            )
        if year or month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id)
            if year:
                q = q.filter(DimTime.time_year == year)
            if month:
                q = q.filter(DimTime.time_month == month)
        if store:
            q = q.join(DimStore, MonthlySummary.store_id == DimStore.id).filter(DimStore.code == store)

        # 排序（用RMB字段排序）
        sort_column_map = {
            "ad_spend": (MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate),
            "ad_sales": (MonthlySummary.ad_sales_usd * MonthlySummary.exchange_rate),
            "acos": MonthlySummary.acos,
            "roas": MonthlySummary.roas,
            "ctr": MonthlySummary.ctr,
            "cpc": MonthlySummary.cpc,
            "impressions": MonthlySummary.impressions,
            "clicks": MonthlySummary.clicks,
            "ad_orders": MonthlySummary.ad_orders,
            "conversion_rate": MonthlySummary.conversion_rate,
            "product_name": DimProduct.product_name,
            "asin": DimProduct.asin,
        }

        sort_col = sort_column_map.get(sort_by, MonthlySummary.ad_spend_usd * MonthlySummary.exchange_rate)
        if sort_order.lower() == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        # 总数
        total = q.count()

        # 分页
        offset = (page - 1) * page_size
        rows = q.offset(offset).limit(page_size).all()

        data = []
        for row in rows:
            spend_rmb = float(row.ad_spend_rmb or 0)
            sales_rmb = float(row.ad_sales_rmb or 0)
            # ACOS/ROAS 从RMB口径计算，与数据看板一致
            acos = (spend_rmb / sales_rmb * 100) if sales_rmb > 0 else 0
            roas = (sales_rmb / spend_rmb) if spend_rmb > 0 else 0
            data.append({
                "product_name": row.product_name,
                "asin": row.asin,
                "ad_spend": round(spend_rmb, 2),
                "ad_sales": round(sales_rmb, 2),
                "acos": round(acos, 2),
                "roas": round(roas, 2),
                "ctr": round(float(row.ctr or 0) * 100, 2),
                "cpc": round(spend_rmb / int(row.clicks or 0), 2) if int(row.clicks or 0) > 0 else 0,
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "ad_orders": int(row.ad_orders or 0),
                "conversion_rate": round(float(row.conversion_rate or 0) * 100, 2),
            })

        return {"data": data, "total": total, "page": page, "page_size": page_size}

    except Exception as e:
        return {"detail": str(e)}
