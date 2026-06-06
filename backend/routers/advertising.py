from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String
from database import get_db
from models import MonthlySummary, DimCountry, DimTime, DimProduct

router = APIRouter()


@router.get("/summary")
def get_ad_summary(
    country: str = Query(None, description="国家代码"),
    year_month: str = Query(None, description="年月，如 2026-05"),
    db: Session = Depends(get_db),
):
    try:
        q = db.query(
            func.sum(MonthlySummary.ad_spend_usd).label("total_ad_spend"),
            func.avg(MonthlySummary.acos).label("avg_acos"),
            func.avg(MonthlySummary.roas).label("avg_roas"),
        )

        if country:
            q = q.join(DimCountry, MonthlySummary.country_id == DimCountry.id).filter(
                DimCountry.code == country.upper()
            )
        if year_month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(
                DimTime.year_month == year_month
            )

        row = q.one()

        return {
            "total_ad_spend": float(row.total_ad_spend or 0),
            "avg_acos": float(row.avg_acos or 0),
            "avg_roas": float(row.avg_roas or 0),
        }

    except Exception as e:
        return {"detail": str(e)}


@router.get("/detail")
def get_ad_detail(
    country: str = Query(None, description="国家代码"),
    year_month: str = Query(None, description="年月"),
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
            MonthlySummary.ad_spend_usd.label("ad_spend"),
            MonthlySummary.ad_sales_usd.label("ad_sales"),
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
        if year_month:
            q = q.join(DimTime, MonthlySummary.time_id == DimTime.id).filter(
                DimTime.year_month == year_month
            )

        # 排序
        sort_column_map = {
            "ad_spend": MonthlySummary.ad_spend_usd,
            "ad_sales": MonthlySummary.ad_sales_usd,
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

        sort_col = sort_column_map.get(sort_by, MonthlySummary.ad_spend_usd)
        if sort_order.lower() == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        # 总数
        total = q.count()

        # 分页
        offset = (page - 1) * page_size
        rows = q.offset(offset).limit(page_size).all()

        data = [
            {
                "product_name": row.product_name,
                "asin": row.asin,
                "ad_spend": float(row.ad_spend or 0),
                "ad_sales": float(row.ad_sales or 0),
                "acos": float(row.acos or 0),
                "roas": float(row.roas or 0),
                "ctr": float(row.ctr or 0),
                "cpc": float(row.cpc or 0),
                "impressions": int(row.impressions or 0),
                "clicks": int(row.clicks or 0),
                "ad_orders": int(row.ad_orders or 0),
                "conversion_rate": float(row.conversion_rate or 0),
            }
            for row in rows
        ]

        return {"data": data, "total": total, "page": page, "page_size": page_size}

    except Exception as e:
        return {"detail": str(e)}
