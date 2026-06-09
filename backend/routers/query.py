from fastapi import APIRouter, Depends, Query as FastAPIQuery, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from database import get_db
from models import MonthlySummary, DimCountry, DimProduct, DimTime, DimProductCost, DimStore

router = APIRouter()


def _build_base_query(db, store_id=None, country_id=None, year=None, month=None):
    """构建公共筛选条件，返回 (time_ids, ms_filters)"""
    time_query = db.query(DimTime.id)
    if year:
        time_query = time_query.filter(DimTime.time_year == year)
    if month:
        time_query = time_query.filter(DimTime.time_month == month)
    time_ids = [r[0] for r in time_query.all()]

    filters = []
    if country_id:
        filters.append(MonthlySummary.country_id == country_id)
    if time_ids:
        filters.append(MonthlySummary.time_id.in_(time_ids))
    if store_id:
        filters.append(MonthlySummary.store_id == store_id)

    return time_ids, filters


@router.get("/country-summary")
def get_country_summary(
    store: str = FastAPIQuery(None, description="店铺代码"),
    year: int = FastAPIQuery(None, description="年份"),
    month: int = FastAPIQuery(None, description="月份"),
    db: Session = Depends(get_db),
):
    """按国家分组汇总 — 用于查看店铺下各国家的总数据"""
    try:
        store_id = None
        if store:
            store_obj = db.query(DimStore).filter(DimStore.code == store).first()
            if store_obj:
                store_id = store_obj.id
            else:
                return {"data": []}

        _, filters = _build_base_query(db, store_id=store_id, year=year, month=month)

        q = (
            db.query(
                DimCountry.code.label("country_code"),
                DimCountry.name.label("country_name"),
                func.coalesce(func.sum(MonthlySummary.order_count), 0).label("order_count"),
                func.coalesce(func.sum(MonthlySummary.product_sales_usd), 0).label("product_sales_usd"),
                func.coalesce(func.sum(MonthlySummary.product_sales_rmb), 0).label("product_sales_rmb"),
                func.coalesce(func.sum(MonthlySummary.commission_usd), 0).label("commission_usd"),
                func.coalesce(func.sum(MonthlySummary.fba_fee_usd), 0).label("fba_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.ad_spend_usd), 0).label("ad_spend_usd"),
                func.coalesce(func.sum(MonthlySummary.storage_fee_usd), 0).label("storage_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.returns_fee_usd), 0).label("returns_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.inbound_fee_usd), 0).label("inbound_fee_usd"),
                func.coalesce(func.sum(MonthlySummary.product_cost_rmb), 0).label("product_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.freight_cost_rmb), 0).label("freight_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.net_profit_rmb), 0).label("net_profit_rmb"),
            )
            .join(DimCountry, MonthlySummary.country_id == DimCountry.id)
        )

        if filters:
            q = q.filter(*filters)

        q = q.group_by(DimCountry.id, DimCountry.code, DimCountry.name)
        # 过滤掉没有实际订单的国家（导入时生成的空记录）
        q = q.having(func.sum(MonthlySummary.order_count) > 0)
        rows = q.all()

        # 计算总销售额用于占比
        total_sales_rmb = sum(float(r.product_sales_rmb or 0) for r in rows)

        data = []
        for r in rows:
            sales_rmb = float(r.product_sales_rmb or 0)
            net = float(r.net_profit_rmb or 0)
            data.append({
                "country_code": r.country_code,
                "country_name": r.country_name,
                "order_count": int(r.order_count or 0),
                "product_sales_usd": round(float(r.product_sales_usd or 0), 2),
                "product_sales_rmb": round(sales_rmb, 2),
                "commission_usd": round(float(r.commission_usd or 0), 2),
                "fba_fee_usd": round(float(r.fba_fee_usd or 0), 2),
                "ad_spend_usd": round(float(r.ad_spend_usd or 0), 2),
                "storage_fee_usd": round(float(r.storage_fee_usd or 0), 2),
                "returns_fee_usd": round(float(r.returns_fee_usd or 0), 2),
                "inbound_fee_usd": round(float(r.inbound_fee_usd or 0), 2),
                "product_cost_rmb": round(float(r.product_cost_rmb or 0), 2),
                "freight_cost_rmb": round(float(r.freight_cost_rmb or 0), 2),
                "net_profit_rmb": round(net, 2),
                "net_profit_rate": round(net / sales_rmb * 100, 1) if sales_rmb > 0 else 0,
                "sales_pct": round(sales_rmb / total_sales_rmb * 100, 1) if total_sales_rmb > 0 else 0,
            })

        # 按销售额降序
        data.sort(key=lambda x: x["product_sales_rmb"], reverse=True)
        return {"data": data}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly-summary")
def get_monthly_summary(
    country: str = FastAPIQuery("", description="国家代码，空=全部国家"),
    year: int = FastAPIQuery(None, description="年份"),
    month: int = FastAPIQuery(None, description="月份"),
    store: str = FastAPIQuery(None, description="店铺代码"),
    keyword: str = FastAPIQuery(None, description="搜索关键词（ASIN或产品名称）"),
    sort_by: str = FastAPIQuery("net_profit_rmb", description="排序字段"),
    sort_order: str = FastAPIQuery("desc", description="排序方向 asc/desc"),
    page: int = FastAPIQuery(1, ge=1),
    page_size: int = FastAPIQuery(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """按产品汇总的月度数据"""
    try:
        country_id = None
        if country:
            country_obj = db.query(DimCountry).filter(DimCountry.code == country.upper()).first()
            if not country_obj:
                return {"data": [], "total": 0, "page": page, "page_size": page_size, "totals": {}}
            country_id = country_obj.id

        store_id = None
        if store:
            store_obj = db.query(DimStore).filter(DimStore.code == store).first()
            if store_obj:
                store_id = store_obj.id
            else:
                return {"data": [], "total": 0, "page": page, "page_size": page_size, "totals": {}}

        time_ids, filters = _build_base_query(db, store_id=store_id, country_id=country_id, year=year, month=month)

        # === 全局汇总（不受分页影响）===
        total_q = db.query(
            func.coalesce(func.sum(MonthlySummary.order_count), 0).label("order_count"),
            func.coalesce(func.sum(MonthlySummary.product_sales_usd), 0).label("product_sales_usd"),
            func.coalesce(func.sum(MonthlySummary.product_sales_rmb), 0).label("product_sales_rmb"),
            func.coalesce(func.sum(MonthlySummary.commission_usd), 0).label("commission_usd"),
            func.coalesce(func.sum(MonthlySummary.fba_fee_usd), 0).label("fba_fee_usd"),
            func.coalesce(func.sum(MonthlySummary.ad_spend_usd), 0).label("ad_spend_usd"),
            func.coalesce(func.sum(MonthlySummary.storage_fee_usd), 0).label("storage_fee_usd"),
            func.coalesce(func.sum(MonthlySummary.returns_fee_usd), 0).label("returns_fee_usd"),
            func.coalesce(func.sum(MonthlySummary.inbound_fee_usd), 0).label("inbound_fee_usd"),
            func.coalesce(func.sum(MonthlySummary.product_cost_rmb), 0).label("product_cost_rmb"),
            func.coalesce(func.sum(MonthlySummary.freight_cost_rmb), 0).label("freight_cost_rmb"),
            func.coalesce(func.sum(MonthlySummary.net_profit_rmb), 0).label("net_profit_rmb"),
        )
        if filters:
            total_q = total_q.filter(*filters)
        total_row = total_q.one()
        total_sales_rmb = float(total_row.product_sales_rmb or 0)
        total_net = float(total_row.net_profit_rmb or 0)
        totals = {
            "order_count": int(total_row.order_count or 0),
            "product_sales_usd": round(float(total_row.product_sales_usd or 0), 2),
            "product_sales_rmb": round(total_sales_rmb, 2),
            "commission_usd": round(float(total_row.commission_usd or 0), 2),
            "fba_fee_usd": round(float(total_row.fba_fee_usd or 0), 2),
            "ad_spend_usd": round(float(total_row.ad_spend_usd or 0), 2),
            "storage_fee_usd": round(float(total_row.storage_fee_usd or 0), 2),
            "returns_fee_usd": round(float(total_row.returns_fee_usd or 0), 2),
            "inbound_fee_usd": round(float(total_row.inbound_fee_usd or 0), 2),
            "product_cost_rmb": round(float(total_row.product_cost_rmb or 0), 2),
            "freight_cost_rmb": round(float(total_row.freight_cost_rmb or 0), 2),
            "net_profit_rmb": round(total_net, 2),
            "net_profit_rate": round(total_net / total_sales_rmb * 100, 1) if total_sales_rmb > 0 else 0,
        }

        # === 产品明细 ===
        ms_on = [MonthlySummary.product_id == DimProduct.id]
        if country_id:
            ms_on.append(MonthlySummary.country_id == country_id)
        if time_ids:
            ms_on.append(MonthlySummary.time_id.in_(time_ids))
        if store_id:
            ms_on.append(MonthlySummary.store_id == store_id)

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
                func.coalesce(func.sum(MonthlySummary.promo_rebate_usd), 0).label("promo_rebate_usd"),
                func.coalesce(func.sum(MonthlySummary.promo_rebate_tax_usd), 0).label("promo_rebate_tax_usd"),
                func.coalesce(func.sum(MonthlySummary.marketplace_withheld_tax_usd), 0).label("marketplace_withheld_tax_usd"),
                func.coalesce(func.sum(MonthlySummary.adjustment_usd), 0).label("adjustment_usd"),
                func.coalesce(func.sum(MonthlySummary.product_cost_rmb), 0).label("ms_product_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.freight_cost_rmb), 0).label("ms_freight_cost_rmb"),
                func.coalesce(func.sum(MonthlySummary.net_profit_rmb), 0).label("ms_net_profit_rmb"),
            )
            .join(MonthlySummary, and_(*ms_on))
            .filter(DimProduct.asin.notlike("Amazon.%"))
            .group_by(DimProduct.id, DimProduct.product_name, DimProduct.asin, DimProduct.sku, DimProduct.color)
            .having(func.sum(MonthlySummary.order_count) > 0)
        )

        if keyword:
            kw = f"%{keyword.strip()}%"
            q = q.filter(
                (DimProduct.asin.like(kw)) | (DimProduct.product_name.like(kw))
            )

        all_rows = q.all()

        # 批量查询产品成本（避免 N+1）
        product_ids = [row.product_id for row in all_rows]
        cost_map = {}
        if product_ids:
            costs = db.query(DimProductCost).filter(DimProductCost.product_id.in_(product_ids)).all()
            for pc in costs:
                pid = pc.product_id
                if pid not in cost_map:
                    cost_map[pid] = {"cost_rmb": float(pc.cost_rmb or 0), "freight_per_unit": float(pc.freight_per_unit or 0)}

        results = []
        for row in all_rows:
            order_count = int(row.order_count or 0)
            sales_usd = float(row.product_sales_usd or 0)
            sales_rmb = float(row.product_sales_rmb or 0)
            product_cost = float(row.ms_product_cost_rmb or 0)
            freight_cost = float(row.ms_freight_cost_rmb or 0)
            net = float(row.ms_net_profit_rmb or 0)
            rate = round(net / sales_rmb * 100, 1) if sales_rmb > 0 else 0

            pc = cost_map.get(row.product_id, {})
            results.append({
                "product_name": row.product_name or "-",
                "asin": row.asin,
                "sku": row.sku,
                "color": row.color or "-",
                "cost_rmb": pc.get("cost_rmb", 0),
                "freight_per_unit": pc.get("freight_per_unit", 0),
                "order_count": order_count,
                "product_sales_usd": round(sales_usd, 2),
                "product_sales_rmb": round(sales_rmb, 2),
                "commission_usd": round(float(row.commission_usd or 0), 2),
                "fba_fee_usd": round(float(row.fba_fee_usd or 0), 2),
                "ad_spend_usd": round(float(row.ad_spend_usd or 0), 2),
                "storage_fee_usd": round(float(row.storage_fee_usd or 0) + float(row.returns_fee_usd or 0) + float(row.inbound_fee_usd or 0), 2),
                "promo_rebate_usd": round(float(row.promo_rebate_usd or 0), 2),
                "promo_rebate_tax_usd": round(float(row.promo_rebate_tax_usd or 0), 2),
                "marketplace_withheld_tax_usd": round(float(row.marketplace_withheld_tax_usd or 0), 2),
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

        return {"data": data, "total": total, "page": page, "page_size": page_size, "totals": totals}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))
