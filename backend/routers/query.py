from fastapi import APIRouter, Depends, Query as FastAPIQuery
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from database import get_db
from models import MonthlySummary, DimCountry, DimProduct, DimTime

router = APIRouter()


@router.get("/monthly-summary")
def get_monthly_summary(
    country: str = FastAPIQuery("US", description="国家代码"),
    year: int = FastAPIQuery(None, description="年份"),
    month: int = FastAPIQuery(None, description="月份"),
    store: str = FastAPIQuery(None, description="店铺代码"),
    keyword: str = FastAPIQuery(None, description="搜索关键词（ASIN或产品名称）"),
    sort_by: str = FastAPIQuery("net_profit_rmb", description="排序字段"),
    sort_order: str = FastAPIQuery("desc", description="排序方向 asc/desc"),
    page: int = FastAPIQuery(1, ge=1),
    page_size: int = FastAPIQuery(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """按产品汇总的月度数据（所有产品都会出现，无交易的销量为0）"""
    try:
        country_obj = db.query(DimCountry).filter(DimCountry.code == country.upper()).first()
        if not country_obj:
            return {"data": [], "total": 0, "page": page, "page_size": page_size}
        country_id = country_obj.id

        # 获取 store_id
        store_id = None
        if store:
            from models import DimStore
            store_obj = db.query(DimStore).filter(DimStore.code == store).first()
            if store_obj:
                store_id = store_obj.id
            else:
                return {"data": [], "total": 0, "page": page, "page_size": page_size}

        # 先查出目标时间 ID（支持年/月/全部）
        time_query = db.query(DimTime.id)
        if year:
            time_query = time_query.filter(DimTime.time_year == year)
        if month:
            time_query = time_query.filter(DimTime.time_month == month)
        time_ids = [r[0] for r in time_query.all()]

        # 构建 MonthlySummary 的 on 条件
        ms_on = [
            MonthlySummary.country_id == country_id,
            MonthlySummary.product_id == DimProduct.id,
        ]
        if time_ids:
            ms_on.append(MonthlySummary.time_id.in_(time_ids))
        if store_id:
            ms_on.append(MonthlySummary.store_id == store_id)

        # 从 DimProduct 出发，左连接 MonthlySummary，确保所有产品都出现
        q = (
            db.query(
                DimProduct.id.label("product_id"),
                DimProduct.product_name,
                DimProduct.asin,
                DimProduct.sku,
                DimProduct.color,
                func.coalesce(func.sum(MonthlySummary.order_count), 0).label("order_count"),
                func.coalesce(func.sum(MonthlySummary.product_sales_usd), 0).label("product_sales_usd"),
                func.coalesce(func.sum(MonthlySummary.product_sales_rmb), 0).label("product_sales_rmb"),
                func.coalesce(func.sum(MonthlySummary.commission_usd), 0).label("commission_usd"),
                func.coalesce(func.sum(MonthlySummary.fba_fee_usd), 0).label("fba_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.ad_spend_usd), 0).label("ad_spend_usd"),
                func.coalesce(func.sum(MonthlySummary.storage_fee_usd), 0).label("storage_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.returns_fee_usd), 0).label("returns_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.inbound_fee_usd), 0).label("inbound_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.product_cost_rmb), 0).label("ms_product_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.freight_cost_rmb), 0).label("ms_freight_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.net_profit_rmb), 0).label("ms_net_profit_rmb"),
            )
            .outerjoin(MonthlySummary, and_(*ms_on))
            .filter(DimProduct.asin.notlike("Amazon.%"))
            .group_by(DimProduct.id, DimProduct.product_name, DimProduct.asin, DimProduct.sku, DimProduct.color)
        )

        # 关键词搜索
        if keyword:
            kw = f"%{keyword.strip()}%"
            q = q.filter(
                (DimProduct.asin.like(kw)) | (DimProduct.product_name.like(kw))
            )

        # 获取全部结果用于排序（产品数量有限，不会太多）
        all_rows = q.all()

        # 构建结果
        results = []
        for row in all_rows:
            order_count = int(row.order_count or 0)
            sales_usd = float(row.product_sales_usd or 0)
            sales_rmb = float(row.product_sales_rmb or 0)
            # 采购成本和运费 = 单价 × 下单数量（跟订单挂钩）
            product_cost = float(row.ms_product_cost_rmb or 0)
            freight_cost = float(row.ms_freight_cost_rmb or 0)

            # 净利润直接取预存值（由 _recalculate_all_profit 按当时汇率算好存入）
            net = float(row.ms_net_profit_rmb or 0)
            rate = round(net / sales_rmb * 100, 1) if sales_rmb > 0 else 0

            results.append({
                "product_name": row.product_name or "-",
                "asin": row.asin,
                "sku": row.sku,
                "color": row.color or "-",
                "cost_rmb": 0,
                "freight_per_unit": 0,
                "order_count": order_count,
                "product_sales_usd": round(sales_usd, 2),
                "product_sales_rmb": round(sales_rmb, 2),
                "commission_usd": round(float(row.commission_usd or 0), 2),
                "fba_fee_usd": round(float(row.fba_fee_usd or 0), 2),
                "ad_spend_usd": round(float(row.ad_spend_usd or 0), 2),
                "storage_fee_usd": round(float(row.storage_fee_usd or 0) + float(row.returns_fee_usd or 0) + float(row.inbound_fee_usd or 0), 2),
                "product_cost_rmb": round(product_cost, 2),
                "freight_cost_rmb": round(freight_cost, 2),
                "net_profit_rmb": round(net, 2),
                "net_profit_rate": rate,
            })

        # 排序
        reverse = sort_order.lower() != "asc"
        results.sort(key=lambda r: r.get(sort_by, r.get("net_profit_rmb", 0)), reverse=reverse)

        total = len(results)
        start = (page - 1) * page_size
        data = results[start:start + page_size]

        return {"data": data, "total": total, "page": page, "page_size": page_size}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"detail": str(e)}


@router.get("/transactions")
def get_transactions(
    country: str = FastAPIQuery(None, description="国家代码"),
    date_from: str = FastAPIQuery(None, description="起始日期"),
    date_to: str = FastAPIQuery(None, description="结束日期"),
    sku: str = FastAPIQuery(None, description="SKU"),
    page: int = FastAPIQuery(1, ge=1),
    page_size: int = FastAPIQuery(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """原始交易明细（备用）"""
    try:
        from models import RawTransaction
        q = db.query(RawTransaction)
        if country:
            q = q.join(DimCountry, RawTransaction.country_id == DimCountry.id).filter(DimCountry.code == country.upper())
        if date_from:
            q = q.filter(RawTransaction.transaction_date >= date_from)
        if date_to:
            q = q.filter(RawTransaction.transaction_date <= date_to)
        if sku:
            q = q.filter(RawTransaction.sku == sku)

        total = q.count()
        rows = q.order_by(RawTransaction.transaction_date.desc()).offset((page - 1) * page_size).limit(page_size).all()

        data = [{
            "id": r.id,
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
            "transaction_type": r.transaction_type,
            "sku": r.sku,
            "description": r.description,
            "quantity": r.quantity,
            "product_sales": float(r.product_sales or 0),
            "selling_fee": float(r.selling_fee or 0),
            "fba_fee": float(r.fba_fee or 0),
            "total": float(r.total or 0),
        } for r in rows]

        return {"data": data, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        return {"detail": str(e)}
