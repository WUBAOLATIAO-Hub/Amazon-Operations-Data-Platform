import csv
import io
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import (
    DimCountry, DimProduct, DimProductCost, DimTime, DimStore, DimExchangeRate, MonthlySummary, RawTransaction,
    RawAdvertising, RawStorageFee, RawReturns, RawInbound, RawLongTermStorage,
)
from config import UPLOAD_DIR

router = APIRouter()


def _detect_country_from_data(db: Session, header, rows):
    """从数据文件中自动检测国家: marketplace/country_code → US/UK/DE/CA/MX"""
    mp_idx = None; cc_idx = None
    for i, h in enumerate(header):
        hl = h.lower().strip() if h else ""
        if hl == 'marketplace': mp_idx = i  # 精确匹配，避免 "marketplace withheld tax"
        if hl in ('country_code', 'country'): cc_idx = i
    for row in rows[:20]:
        vals = []
        if mp_idx is not None and len(row) > mp_idx: vals.append(str(row[mp_idx] or '').lower())
        if cc_idx is not None and len(row) > cc_idx: vals.append(str(row[cc_idx] or '').lower())
        for v in vals:
            if v in ('mx', 'mex', 'amazon.com.mx', 'mexico'): return 'MX'
            if v in ('ca', 'can', 'amazon.ca', 'canada'): return 'CA'
            if v in ('us', 'usa', 'amazon.com', 'united states'): return 'US'
            if v in ('uk', 'gb', 'gbr', 'amazon.co.uk', 'united kingdom'): return 'UK'
            if v in ('de', 'deu', 'amazon.de', 'germany'): return 'DE'
    return None


def _get_or_default_store(db: Session, store: str = None):
    """获取店铺对象，自动去除首尾空格，未指定返回 None"""
    if not store:
        return None
    store = store.strip()
    return db.query(DimStore).filter(DimStore.code == store).first()


def _get_or_create_time(db: Session, year: int, month: int) -> DimTime:
    year_month = f"{year}-{month:02d}"
    time_obj = db.query(DimTime).filter(DimTime.year_month == year_month).first()
    if not time_obj:
        time_obj = DimTime(time_year=year, time_month=month, year_month=year_month)
        db.add(time_obj)
        db.flush()
    return time_obj


def _parse_month_string(month_str: str):
    """将各种月份格式转为 (year, month)，支持格式:
    'May-26', 'Apr-26' → (2026, 5), (2026, 4)
    '2026-05', '2026/5' → (2026, 5)
    '2026-05-01', '2026/5/1' → (2026, 5)
    返回 (year_int, month_int) 或 (None, None)
    """
    import re
    if not month_str or not month_str.strip():
        return None, None
    s = month_str.strip()
    # 格式1a: 'May-26' → 英文缩写月-两位年
    m = re.search(r'^(\w{3})-(\d{2})$', s)
    # 格式1b: '26-May' → 两位年-英文缩写月
    m2 = re.search(r'^(\d{2})-(\w{3})$', s)
    month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                 "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    if m:
        abbr = m.group(1).lower()
        if abbr in month_map:
            year = int("20" + m.group(2))
            return year, month_map[abbr]
    if m2:
        abbr = m2.group(2).lower()
        if abbr in month_map:
            year = int("20" + m2.group(1))
            return year, month_map[abbr]
    # 格式2: '2026-05', '2026-05-01', '2026/5', '2026/5/1'
    m = re.search(r'(\d{4})[/\-](\d{1,2})', s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        if 1 <= month <= 12:
            return year, month
    return None, None


def _find_time_by_month_str(db: Session, month_str: str):
    """根据月份字符串找到对应的 DimTime，支持多种格式"""
    year, month = _parse_month_string(month_str)
    if year and month:
        standard = f"{year}-{month:02d}"
        time_obj = db.query(DimTime).filter(DimTime.year_month == standard).first()
        if time_obj:
            return time_obj
        return _get_or_create_time(db, year, month)
    return None


def _get_or_create_product(db: Session, asin: str, sku: str = None) -> DimProduct:
    asin = asin.strip() if asin else ""
    if not asin or asin.startswith("Amazon.") or asin.startswith("amzn.gr."):
        return None
    product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
    if not product:
        product = DimProduct(asin=asin, sku=sku or asin)
        db.add(product)
        db.flush()
    elif sku and not product.sku:
        product.sku = sku
        db.flush()
    return product


def _extract_real_sku(sku: str):
    """从 amzn.gr.XXX-XXXX-XXXX-xxx-x 中提取真实SKU (XXX-XXXX-XXXX)"""
    if sku and sku.startswith("amzn.gr."):
        import re as _re
        # amzn.gr.WH-O0WE-F4CW-fkUFJmAenNF5IeG1-LN
        # → parts: ['amzn.gr.WH', 'O0WE', 'F4CW', ...]
        # → 真实SKU: WH-O0WE-F4CW (parts[0]最后一段 + parts[1] + parts[2])
        # amzn.gr.MGT-VH280B-48Beige-4ZwgOd8M5v-GD
        # → 真实SKU: MGT-VH280B-48Beige (前缀可以是2-5字符)
        parts = sku.split("-")
        if len(parts) >= 3:
            prefix = parts[0].split(".")[-1]  # 'amzn.gr.MGT' → 'MGT'
            candidate = f"{prefix}-{parts[1]}-{parts[2]}"
            # 放宽匹配：前缀2-5字符，中间段1-10字符，末段1-10字符
            if _re.match(r'^[A-Z0-9]{2,5}-[A-Z0-9]{1,10}-[A-Z0-9]{1,10}$', candidate.upper()):
                return candidate
    return None


def _get_exchange_rate(db: Session, country_obj, import_year=None, import_month=None) -> Decimal:
    """获取汇率：优先从 dim_exchange_rate 按(国家,月份)查找，否则按国家给默认值"""
    ym = None
    if import_year and import_month:
        ym = f"{import_year}-{import_month:02d}"
    if ym:
        er = db.query(DimExchangeRate).filter(
            DimExchangeRate.country_id == country_obj.id,
            DimExchangeRate.year_month == ym,
        ).first()
        if er and er.rate and Decimal(str(er.rate)) != 0:
            return Decimal(str(er.rate))
    # 无月份匹配时，取该国家任意一条汇率记录
    er = db.query(DimExchangeRate).filter(DimExchangeRate.country_id == country_obj.id).first()
    if er and er.rate and Decimal(str(er.rate)) != 0:
        return Decimal(str(er.rate))
    # 默认值：按国家货币
    defaults = {'US': '6.8', 'UK': '9.0', 'DE': '7.5', 'CA': '5.0', 'MX': '0.4'}
    return Decimal(defaults.get(country_obj.code, '6.8'))


def _find_product_by_sku(db: Session, sku: str) -> DimProduct:
    """通过 SKU 查找产品（优先找 ASIN 以 B0 开头的）"""
    if not sku:
        return None
    # 先找 ASIN 以 B0 开头的产品（来自产品信息表）
    product = db.query(DimProduct).filter(
        DimProduct.sku == sku,
        DimProduct.asin.like("B0%")
    ).first()
    if product:
        return product
    # 再找任意匹配
    product = db.query(DimProduct).filter(DimProduct.sku == sku).first()
    if product:
        return product
    return None


def _get_or_create_monthly_summary(
    db: Session, country_id: int, product_id: int, time_id: int, store_id: int = None
) -> MonthlySummary:
    filters = [
        MonthlySummary.country_id == country_id,
        MonthlySummary.product_id == product_id,
        MonthlySummary.time_id == time_id,
    ]
    if store_id:
        filters.append(MonthlySummary.store_id == store_id)
    summary = (
        db.query(MonthlySummary)
        .filter(*filters)
        .first()
    )
    if not summary:
        summary = MonthlySummary(
            country_id=country_id,
            product_id=product_id,
            time_id=time_id,
            store_id=store_id,
        )
        db.add(summary)
        db.flush()
    elif store_id and not summary.store_id:
        summary.store_id = store_id
    return summary


def _safe_decimal(value, default=0) -> Decimal:
    if value is None:
        return Decimal(str(default))
    s = str(value).strip().replace(",", "").replace("$", "").replace("¥", "").replace("%", "")
    if s == "" or s == "-":
        return Decimal(str(default))
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(str(default))


def _safe_int(value, default=0) -> int:
    if value is None:
        return default
    s = str(value).strip().replace(",", "")
    if s == "" or s == "-":
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def _detect_date_format(date_str: str):
    """尝试解析多种日期格式"""
    date_str = date_str.strip()
    # 移除时区后缀 (PDT, PST, EST, GMT-7, GMT+5:30 等)
    date_str_clean = re.sub(r'\s+[A-Z]{2,4}[\d\-+:]*$', '', date_str)
    # 统一 a.m./p.m. → AM/PM（西班牙语格式用 .replace 因为 \b 和 . 冲突）
    date_str_clean = date_str_clean.replace('a.m.', 'AM').replace('p.m.', 'PM')
    date_str_clean = date_str_clean.replace('A.M.', 'AM').replace('P.M.', 'PM')
    formats = [
        "%d %b %Y %I:%M:%S %p",    # 5 may 2026 5:08:09 AM (MX无逗号格式)
        "%b %d, %Y %I:%M:%S %p",   # May 1, 2026 5:46:45 AM
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str_clean, fmt)
        except ValueError:
            continue
    return None


# ============================================================
# POST /transaction: 导入交易记录 CSV
# ============================================================
@router.post("/transaction")
async def import_transaction(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码，如 US"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在，请先在 dim_country 中创建"}
        store_obj = _get_or_default_store(db, store)
        if not store_obj:
            return {"detail": f"店铺 {store} 不存在"}

        # 清除该店铺的旧交易数据，防止重复导入
        db.query(RawTransaction).filter(RawTransaction.store_id == store_obj.id).delete()
        db.query(MonthlySummary).filter(MonthlySummary.store_id == store_obj.id).delete()
        db.flush()

        content = await file.read()
        # 尝试多种编码
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件，请确认编码格式"}

        lines = text.splitlines()

        # 前9行是元数据，跳过，第10行是表头
        if len(lines) < 10:
            return {"detail": "CSV 行数不足，至少需要10行（9行元数据+1行表头）"}

        header_line = lines[9]
        data_rows = lines[10:]

        reader = csv.DictReader(io.StringIO(header_line + "\n" + "\n".join(data_rows)))
        headers = reader.fieldnames
        if not headers:
            return {"detail": "无法解析 CSV 表头"}

        # 多语言字段映射
        MULTI_LANG_MAP = {
            # Spanish → English
            'fecha/hora': 'date/time',
            'id. de liquidación': 'settlement id',
            'tipo': 'type',
            'pedido': 'Order', 'reembolso': 'Refund',
            'id. del pedido': 'order id',
            'sku': 'sku',
            'descripción': 'description',
            'cantidad': 'quantity',
            'marketplace': 'marketplace',
            'cumplimiento': 'fulfillment',
            'ventas de productos': 'product sales',
            'impuesto de ventas de productos': 'product sales tax',
            'créditos de envío': 'shipping credits',
            'impuesto de abono de envío': 'shipping credits tax',
            'créditos por envoltorio de regalo': 'gift wrap credits',
            'descuentos promocionales': 'promotional rebates',
            'impuesto de reembolsos promocionales': 'promotional rebates tax',
            'impuesto de retenciones en la plataforma': 'marketplace withheld tax',
            'tarifas de venta': 'selling fees',
            'tarifas fba': 'fba fees',
            'tarifas de otra transacción': 'other transaction fees',
            'otro': 'other',
            'total': 'total',
            'estado de la transacción': 'transaction_status',
            'fecha de liberación de la transacción': 'transaction_release_date',
        }
        # 字段映射（去空格、小写化）
        def map_header(h):
            h = h.strip().lower()
            # 先查多语言映射
            if h in MULTI_LANG_MAP:
                h = MULTI_LANG_MAP[h]
            mapping = {
                "date/time": "transaction_date",
                "date / time": "transaction_date",
                "settlement id": "settlement_id",
                "type": "transaction_type",
                "order id": "order_id",
                "sku": "sku",
                "description": "description",
                "quantity": "quantity",
                "marketplace": "marketplace",
                "fulfillment": "fulfillment",
                "order city": "order_city",
                "order state": "order_state",
                "order postal": "order_postal",
                "tax collection model": "tax_collection_model",
                "product sales": "product_sales",
                "product sales tax": "product_sales_tax",
                "shipping credits": "shipping_credits",
                "shipping credits tax": "shipping_credits_tax",
                "gift wrap credits": "gift_wrap_credits",
                "giftwrap credits tax": "giftwrap_credits_tax",
                "regulatory fee": "regulatory_fee",
                "tax on regulatory fee": "tax_on_regulatory_fee",
                "promotional rebates": "promotional_rebates",
                "promotional rebates tax": "promotional_rebates_tax",
                "marketplace withheld tax": "marketplace_withheld_tax",
                "selling fees": "selling_fee",
                "fba fees": "fba_fee",
                "other transaction fees": "other_transaction_fee",
                "other": "other_amount",
                "total": "total",
                "status": "transaction_status",
                "release date": "transaction_release_date",
            }
            return mapping.get(h, h)

        # 按 SKU 聚合用于 monthly_summary（仅 Order/Refund）
        sku_aggregation = {}  # key: (sku, year, month) -> dict
        adj_aggregation = {}  # key: (sku, year, month) -> {"total": Decimal, "qty": int}
        row_count = 0
        type_counts = {}

        for row in reader:
            if not row:
                continue

            mapped = {}
            for header_name, value in row.items():
                field = map_header(header_name)
                mapped[field] = value.strip() if value else ""

            # 解析日期
            date_str = mapped.get("transaction_date", "")
            txn_date = _detect_date_format(date_str)
            if not txn_date:
                continue  # 跳过无法解析日期的行

            txn_type = mapped.get("transaction_type", "").strip()
            # 西班牙语类型转英文
            if txn_type.lower() == 'pedido': txn_type = 'Order'
            elif txn_type.lower() == 'reembolso': txn_type = 'Refund'
            type_counts[txn_type] = type_counts.get(txn_type, 0) + 1

            sku = mapped.get("sku", "").strip()
            asin = sku.split("-")[0] if sku and "-" in sku else sku

            is_replacement = sku.startswith("amzn.gr.") if sku else False
            real_sku = _extract_real_sku(sku) if is_replacement else None
            effective_sku = real_sku if real_sku else sku

            product_sales = _safe_decimal(mapped.get("product_sales"))
            selling_fee = _safe_decimal(mapped.get("selling_fee"))
            fba_fee = _safe_decimal(mapped.get("fba_fee"))
            quantity = _safe_int(mapped.get("quantity"))
            total = _safe_decimal(mapped.get("total"))

            # 所有类型都写入 raw_transactions（全量存储）
            raw = RawTransaction(
                country_id=country_obj.id,
                store_id=store_obj.id,
                transaction_date=txn_date,
                settlement_id=mapped.get("settlement_id", ""),
                transaction_type=txn_type,
                order_id=mapped.get("order_id", ""),
                sku=sku,
                description=mapped.get("description", ""),
                quantity=quantity,
                marketplace=mapped.get("marketplace", ""),
                fulfillment=mapped.get("fulfillment", ""),
                order_city=mapped.get("order_city", ""),
                order_state=mapped.get("order_state", ""),
                order_postal=mapped.get("order_postal", ""),
                tax_collection_model=mapped.get("tax_collection_model", ""),
                product_sales=product_sales,
                product_sales_tax=_safe_decimal(mapped.get("product_sales_tax")),
                shipping_credits=_safe_decimal(mapped.get("shipping_credits")),
                shipping_credits_tax=_safe_decimal(mapped.get("shipping_credits_tax")),
                gift_wrap_credits=_safe_decimal(mapped.get("gift_wrap_credits")),
                giftwrap_credits_tax=_safe_decimal(mapped.get("giftwrap_credits_tax")),
                regulatory_fee=_safe_decimal(mapped.get("regulatory_fee")),
                tax_on_regulatory_fee=_safe_decimal(mapped.get("tax_on_regulatory_fee")),
                promotional_rebates=_safe_decimal(mapped.get("promotional_rebates")),
                promotional_rebates_tax=_safe_decimal(mapped.get("promotional_rebates_tax")),
                marketplace_withheld_tax=_safe_decimal(mapped.get("marketplace_withheld_tax")),
                selling_fee=selling_fee,
                fba_fee=fba_fee,
                other_transaction_fee=_safe_decimal(mapped.get("other_transaction_fee")),
                other_amount=_safe_decimal(mapped.get("other_amount")),
                total=total,
                transaction_status=mapped.get("transaction_status", ""),
                transaction_release_date=_detect_date_format(mapped.get("transaction_release_date", "")) if mapped.get("transaction_release_date") else None,
            )
            db.add(raw)
            row_count += 1

            # Adjustment 处理：单独聚合
            if txn_type == "Adjustment":
                adj_key = (effective_sku, txn_date.year, txn_date.month)
                if adj_key not in adj_aggregation:
                    adj_aggregation[adj_key] = {"total": Decimal("0"), "qty": 0}
                adj_aggregation[adj_key]["total"] += total
                order_id_val = mapped.get("order_id", "")
                if not order_id_val or not str(order_id_val).strip():
                    adj_aggregation[adj_key]["qty"] += (1 if total > 0 else -1 if total < 0 else 0)
                continue

            # 仅 Order/Refund 参与 monthly_summary 聚合
            if txn_type not in ("Order", "Refund"):
                continue

            year = txn_date.year
            month = txn_date.month
            key = (effective_sku, year, month)
            if key not in sku_aggregation:
                sku_aggregation[key] = {
                    "product_sales": Decimal("0"),
                    "selling_fee": Decimal("0"),
                    "fba_fee": Decimal("0"),
                    "order_count": 0,
                    "quantity": 0,
                    "order_qty": 0,
                    "promo_rebate": Decimal("0"),
                    "promo_rebate_tax": Decimal("0"),
                    "marketplace_withheld_tax": Decimal("0"),
                }
            agg = sku_aggregation[key]
            # 总收入 = product_sales + shipping_credits + gift_wrap_credits（不含 promotional_rebates）
            shipping = _safe_decimal(mapped.get("shipping_credits"))
            promo = _safe_decimal(mapped.get("promotional_rebates"))
            promo_tax = _safe_decimal(mapped.get("promotional_rebates_tax"))
            mkt_tax = _safe_decimal(mapped.get("marketplace_withheld_tax"))
            gift = _safe_decimal(mapped.get("gift_wrap_credits"))
            agg["product_sales"] += product_sales + shipping + gift
            agg["promo_rebate"] += promo
            agg["promo_rebate_tax"] += promo_tax
            agg["marketplace_withheld_tax"] += mkt_tax
            agg["selling_fee"] += selling_fee
            agg["fba_fee"] += fba_fee
            agg["order_count"] += 1
            # Refund 数量为负（净销量）
            if txn_type == "Refund":
                agg["quantity"] -= abs(quantity)
            else:
                agg["quantity"] += abs(quantity)
                if not is_replacement:
                    agg["order_qty"] += abs(quantity)

        # 按 SKU 聚合写入 monthly_summary
        summary_count = 0

        for (sku, year, month), agg in sku_aggregation.items():
            # 先通过 SKU 查找已有产品，找不到则用 SKU 前缀作为 ASIN
            product = _find_product_by_sku(db, sku)
            if not product:
                asin = sku.split("-")[0] if sku and "-" in sku else sku
                product = _get_or_create_product(db, asin, sku)
            if not product:
                continue
            time_obj = _get_or_create_time(db, year, month)
            exchange_rate = _get_exchange_rate(db, country_obj, year, month)

            summary = _get_or_create_monthly_summary(db, country_obj.id, product.id, time_obj.id, store_id=store_obj.id)

            summary.product_sales_usd = agg["product_sales"]
            summary.commission_usd = agg["selling_fee"]
            summary.fba_fee_usd = agg["fba_fee"]
            summary.promo_rebate_usd = agg["promo_rebate"]
            summary.promo_rebate_tax_usd = agg["promo_rebate_tax"]
            summary.marketplace_withheld_tax_usd = agg["marketplace_withheld_tax"]
            summary.exchange_rate = exchange_rate
            summary.product_sales_rmb = (agg["product_sales"] * exchange_rate).quantize(Decimal("0.01"))
            summary.order_count = agg["quantity"]  # 净销量用于显示
            summary.order_qty = agg["order_qty"]   # 下单数量（不扣退货）

            # 采购成本和运费按下单数量算，从 dim_product_cost 按月取值
            ym = summary.product_sales_rmb  # placeholder, will use time_obj
            time_obj = db.query(DimTime).filter(DimTime.id == summary.time_id).first()
            ym_str = time_obj.year_month if time_obj else None
            pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id, DimProductCost.year_month == ym_str).first()
            if not pc:
                pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id).first()
            unit_cost = Decimal(str(pc.cost_rmb if pc else 0))
            unit_freight = Decimal(str(pc.freight_per_unit if pc else 0))
            cost_rmb = (unit_cost * agg["order_qty"]).quantize(Decimal("0.01"))
            freight_rmb = (unit_freight * agg["order_qty"]).quantize(Decimal("0.01"))

            summary.product_cost_rmb = cost_rmb
            summary.freight_cost_rmb = freight_rmb

            net = (
                summary.product_sales_rmb
                + summary.commission_usd * exchange_rate
                + summary.fba_fee_usd * exchange_rate
                - cost_rmb
                - freight_rmb
                - Decimal(str(summary.ad_spend_usd or 0)) * exchange_rate
                - Decimal(str(summary.storage_fee_usd or 0)) * exchange_rate
                - Decimal(str(summary.returns_fee_usd or 0)) * exchange_rate
                - Decimal(str(summary.inbound_fee_usd or 0)) * exchange_rate


            ).quantize(Decimal("0.01"))

            summary.net_profit_rmb = net
            if summary.product_sales_rmb != 0:
                summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

            summary_count += 1

        # 处理 Adjustment
        for (sku, adj_year, adj_month), adj_agg in adj_aggregation.items():
            product = _find_product_by_sku(db, sku)
            if not product:
                asin = sku.split("-")[0] if sku and "-" in sku else sku
                product = _get_or_create_product(db, asin, sku)
            if not product:
                continue
            time_obj = _get_or_create_time(db, adj_year, adj_month)
            exchange_rate = _get_exchange_rate(db, country_obj, adj_year, adj_month)
            summary = _get_or_create_monthly_summary(db, country_obj.id, product.id, time_obj.id, store_id=store_obj.id)
            summary.adjustment_usd = (summary.adjustment_usd or Decimal("0")) + adj_agg["total"]
            # 无 order_id 的 Adjustment：调整 order_qty 和成本
            if adj_agg["qty"] != 0:
                summary.order_qty = (summary.order_qty or 0) + adj_agg["qty"]
                pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id, DimProductCost.year_month == f"{adj_year}-{adj_month:02d}").first()
                if not pc:
                    pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id).first()
                if pc:
                    summary.product_cost_rmb = (Decimal(str(pc.cost_rmb or 0)) * summary.order_qty).quantize(Decimal("0.01"))
                    summary.freight_cost_rmb = (Decimal(str(pc.freight_per_unit or 0)) * summary.order_qty).quantize(Decimal("0.01"))
            # 重算净利润
            er = exchange_rate
            net = (
                Decimal(str(summary.product_sales_rmb or 0))
                + Decimal(str(summary.commission_usd or 0)) * er
                + Decimal(str(summary.fba_fee_usd or 0)) * er
                + Decimal(str(summary.adjustment_usd or 0)) * er
                - Decimal(str(summary.product_cost_rmb or 0))
                - Decimal(str(summary.freight_cost_rmb or 0))
                - Decimal(str(summary.ad_spend_usd or 0)) * er
                - Decimal(str(summary.storage_fee_usd or 0)) * er
                - Decimal(str(summary.returns_fee_usd or 0)) * er
                - Decimal(str(summary.inbound_fee_usd or 0)) * er
            ).quantize(Decimal("0.01"))
            summary.net_profit_rmb = net
            if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

        # 补建有成本但无交易的产品summary
        _ensure_all_products_have_summary(db, country_obj)

        db.commit()

        return {
            "message": "交易记录导入成功",
            "raw_rows": row_count,
            "summary_rows": summary_count,
            "country": country,
            "type_counts": type_counts,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /product-info: 导入产品信息 XLSX
# ============================================================
@router.post("/product-info")
async def import_product_info(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        import openpyxl

        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            return {"detail": "文件数据不足，至少需要表头+1行数据"}

        header = [str(h).strip() if h else "" for h in rows[0]]

        # 找列索引（精确匹配优先，避免 "产品" 误匹配 "产品运费/台"）
        col_map = {}
        field_names = ["ASIN", "SKU", "产品", "颜色", "成本RMB", "产品运费/台", "汇率", "时间"]
        for i, h in enumerate(header):
            for fn in field_names:
                if h == fn:           # 精确匹配
                    col_map[fn] = i
                    break
            else:
                for fn in field_names:
                    if fn in h:        # 模糊匹配（fallback）
                        col_map[fn] = i
                        break

        if "ASIN" not in col_map:
            return {"detail": "未找到 ASIN 列"}

        count = 0
        for row in rows[1:]:
            if not row or not row[col_map["ASIN"]]:
                continue

            asin = str(row[col_map["ASIN"]]).strip()
            sku = str(row[col_map.get("SKU", 1)]).strip() if "SKU" in col_map and row[col_map["SKU"]] else None
            product_name = str(row[col_map.get("产品", 2)]).strip() if "产品" in col_map and row[col_map["产品"]] else None
            color = str(row[col_map.get("颜色", 3)]).strip() if "颜色" in col_map and row[col_map["颜色"]] else None
            cost_rmb = _safe_decimal(row[col_map["成本RMB"]]) if "成本RMB" in col_map else Decimal("0")
            freight = _safe_decimal(row[col_map["产品运费/台"]]) if "产品运费/台" in col_map else Decimal("0")
            exchange_rate = _safe_decimal(row[col_map["汇率"]]) if "汇率" in col_map else None
            time_val = str(row[col_map["时间"]]).strip() if "时间" in col_map and row[col_map["时间"]] else None

            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                product = DimProduct(asin=asin, sku=sku or asin, product_name=product_name or "", color=color)
                db.add(product)
                db.flush()
            else:
                if sku: product.sku = sku
                if product_name: product.product_name = product_name
                if color: product.color = color

            # 解析月份并写入 dim_product_cost
            ym = None
            if time_val:
                from datetime import datetime
                try:
                    dt = datetime.strptime(time_val[:10], '%Y-%m-%d')
                    ym = dt.strftime('%Y-%m')
                except: pass
            # fallback: 用导入时选择的年月
            if not ym and import_year and import_month:
                ym = f"{import_year}-{import_month:02d}"
            if ym:
                existing_cost = db.query(DimProductCost).filter(
                    DimProductCost.product_id == product.id,
                    DimProductCost.year_month == ym
                ).first()
                if not existing_cost:
                    db.add(DimProductCost(product_id=product.id, year_month=ym, cost_rmb=cost_rmb, freight_per_unit=freight))

            count += 1

        db.commit()

        return {"message": "产品信息导入成功", "rows": count}

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /advertising: 导入广告数据 CSV
# ============================================================
@router.post("/advertising")
async def import_advertising(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}
        store_obj = _get_or_default_store(db, store)
        if not store_obj:
            return {"detail": f"店铺 {store} 不存在"}

        # 清除该店铺旧广告数据，防止重复导入
        db.query(RawAdvertising).filter(RawAdvertising.store_id == store_obj.id).delete()
        db.flush()

        content = await file.read()
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件"}

        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames
        if not headers:
            return {"detail": "无法解析 CSV 表头"}

        # 中文列名映射
        def get_col(row, *names):
            for name in names:
                if name in row:
                    return row[name]
            return None

        # 按 (ASIN, 年月) 聚合 + 写 raw_advertising
        ad_aggregation = {}  # key: (asin, year, month) -> aggregated values
        row_count = 0
        import re as _re

        for row in reader:
            if not row:
                continue

            # 解析 ASIN 从商品字段（格式 ASIN-SKU）
            product_field = get_col(row, "商品", "ASIN", "asin")
            if not product_field:
                continue

            asin = str(product_field).strip().split("-")[0]

            # 解析 time/date 列确定归属月份
            time_val = get_col(row, "time", "日期", "date")
            ad_year, ad_month = None, None
            if time_val:
                time_str = str(time_val).strip()
                # 支持格式: 2026/5/1, 2026-05-01, 2026-05, May-26, 2026/5
                m = _re.search(r'(\d{4})[/\-](\d{1,2})', time_str)
                if m:
                    ad_year = int(m.group(1))
                    ad_month = int(m.group(2))
                else:
                    m = _re.search(r'(\w+)[\-/](\d{2,4})', time_str)
                    if m:
                        month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                     "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                        month_str = m.group(1).lower()[:3]
                        year_str = m.group(2)
                        if month_str in month_map:
                            ad_month = month_map[month_str]
                            ad_year = int(year_str) if len(year_str) == 4 else int("20" + year_str) if len(year_str) == 2 else None

            ad_spend = _safe_decimal(get_col(row, "花费(USD)", "花费(CAD)", "花费(MX)", "花费"))
            ad_sales = _safe_decimal(get_col(row, "销售额(USD)", "销售额(CAD)", "销售额(MX)", "销售额"))
            acos_val = _safe_decimal(get_col(row, "ACOS", "acos"))
            roas_val = _safe_decimal(get_col(row, "ROAS", "roas"))
            ctr_val = _safe_decimal(get_col(row, "CTR", "ctr"))
            cpc_val = _safe_decimal(get_col(row, "CPC", "cpc"))
            impressions_val = _safe_int(get_col(row, "展示次数", "impressions"))
            clicks_val = _safe_int(get_col(row, "点击量", "clicks"))
            ad_orders = _safe_int(get_col(row, "订单数量", "ad_orders"))
            conversion = _safe_decimal(get_col(row, "转化率", "conversion_rate"))
            ntb_orders = _safe_int(get_col(row, "NTB 订单数量"))
            ntb_order_pct = _safe_decimal(get_col(row, "NTB 订单数量百分比"))
            ntb_sales = _safe_decimal(get_col(row, "NTB 销售额(USD)"))
            new_to_brand_pct = _safe_decimal(get_col(row, "品牌新客销售额比例"))
            visible_imp = _safe_int(get_col(row, "可见展示量"))

            # 写入 raw_advertising
            raw_adv = RawAdvertising(
                country_id=country_obj.id,
                store_id=store_obj.id,
                product_field=str(product_field).strip(),
                asin=asin,
                status_val=str(get_col(row, "状态") or "").strip(),
                ad_type=str(get_col(row, "类型") or "").strip(),
                eligibility=str(get_col(row, "商品推广使用资格") or "").strip(),
                sales_usd=ad_sales,
                roas=roas_val,
                conversion_rate=conversion,
                impressions=impressions_val,
                clicks=clicks_val,
                ctr=ctr_val,
                spend_usd=ad_spend,
                cpc=cpc_val,
                orders=ad_orders,
                acos=acos_val,
                ntb_orders=ntb_orders,
                ntb_order_pct=ntb_order_pct,
                ntb_sales_usd=ntb_sales,
                new_to_brand_sales_pct=new_to_brand_pct,
                visible_impressions=visible_imp,
                raw_data=dict(row),
            )
            db.add(raw_adv)

            # 按月聚合: key = (asin, year, month)
            ym_key = (asin, ad_year, ad_month) if ad_year and ad_month else (asin, None, None)
            if ym_key not in ad_aggregation:
                ad_aggregation[ym_key] = {
                    "ad_spend": Decimal("0"),
                    "ad_sales": Decimal("0"),
                    "acos": Decimal("0"),
                    "roas": Decimal("0"),
                    "ctr": Decimal("0"),
                    "cpc": Decimal("0"),
                    "impressions": 0,
                    "clicks": 0,
                    "ad_orders": 0,
                    "conversion_rate": Decimal("0"),
                    "count": 0,
                }
            agg = ad_aggregation[ym_key]
            agg["ad_spend"] += ad_spend
            agg["ad_sales"] += ad_sales
            agg["acos"] += acos_val
            agg["roas"] += roas_val
            agg["ctr"] += ctr_val
            agg["cpc"] += cpc_val
            agg["impressions"] += impressions_val
            agg["clicks"] += clicks_val
            agg["ad_orders"] += ad_orders
            agg["conversion_rate"] += conversion
            agg["count"] += 1
            row_count += 1

        # 更新 monthly_summary
        summary_count = 0

        for (asin, ad_year, ad_month), agg in ad_aggregation.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            exchange_rate = _get_exchange_rate(db, country_obj, ad_year, ad_month)

            # 确定目标月份
            if ad_year and ad_month:
                time_obj = _get_or_create_time(db, ad_year, ad_month)
                time_id = time_obj.id
                filters = [
                    MonthlySummary.product_id == product.id,
                    MonthlySummary.country_id == country_obj.id,
                    MonthlySummary.time_id == time_id,
                ]
                if store_obj:
                    filters.append(MonthlySummary.store_id == store_obj.id)
                summary = db.query(MonthlySummary).filter(*filters).first()
                if not summary:
                    summary = MonthlySummary(
                        country_id=country_obj.id, product_id=product.id, time_id=time_id,
                        store_id=store_obj.id,
                        order_count=0, order_qty=0,
                        product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                        ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                    )
                    db.add(summary)
                target_summaries = [summary]
            else:
                # 无时间信息，更新所有月份（兼容旧逻辑）
                filters = [MonthlySummary.product_id == product.id, MonthlySummary.country_id == country_obj.id]
                if store_obj:
                    filters.append(MonthlySummary.store_id == store_obj.id)
                target_summaries = db.query(MonthlySummary).filter(*filters).all()
                if not target_summaries:
                    continue

            for summary in target_summaries:
                summary.ad_spend_usd = agg["ad_spend"]
                summary.ad_sales_usd = agg["ad_sales"]
                summary.acos = (agg["acos"] / agg["count"]).quantize(Decimal("0.0001")) if agg["count"] else Decimal("0")
                summary.roas = (agg["roas"] / agg["count"]).quantize(Decimal("0.0001")) if agg["count"] else Decimal("0")
                summary.ctr = (agg["ctr"] / agg["count"]).quantize(Decimal("0.0001")) if agg["count"] else Decimal("0")
                summary.cpc = (agg["cpc"] / agg["count"]).quantize(Decimal("0.01")) if agg["count"] else Decimal("0")
                summary.impressions = agg["impressions"]
                summary.clicks = agg["clicks"]
                summary.ad_orders = agg["ad_orders"]
                summary.conversion_rate = (agg["conversion_rate"] / agg["count"]).quantize(Decimal("0.0001")) if agg["count"] else Decimal("0")

                # 重新计算净利润
                net = (
                    summary.product_sales_rmb
                    + Decimal(str(summary.commission_usd or 0)) * exchange_rate
                    + Decimal(str(summary.fba_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.product_cost_rmb or 0))
                    - Decimal(str(summary.freight_cost_rmb or 0))
                    - agg["ad_spend"] * exchange_rate
                    - Decimal(str(summary.storage_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.returns_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.inbound_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_tax_usd or 0)) * exchange_rate
    

                ).quantize(Decimal("0.01"))

                summary.net_profit_rmb = net
                if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                    summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

                summary_count += 1

        db.commit()

        return {
            "message": "广告数据导入成功",
            "csv_rows": row_count,
            "summary_updated": summary_count,
            "country": country,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /storage: 导入仓储费 CSV
# ============================================================
@router.post("/storage")
async def import_storage(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}
        store_obj = _get_or_default_store(db, store)

        content = await file.read()
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件"}

        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames

        def get_col(row, *names):
            for name in names:
                if name in row:
                    return row[name]
            return None

        # 按 (ASIN, 月份) 汇总 + 写 raw_storage_fee
        asin_fees = {}  # key: (asin, month_str)
        row_count = 0
        import re as _re

        for row in reader:
            if not row:
                continue

            asin = None
            for key in ["asin", "ASIN", "fnsku", "FNSKU"]:
                val = get_col(row, key)
                if val:
                    asin = str(val).strip()
                    break

            if not asin:
                continue

            fee = _safe_decimal(get_col(row, "estimated_monthly_storage_fee", "estimated-monthly-storage-fee", "storage_fee"))
            month_str = str(get_col(row, "month_of_charge") or "").strip()

            # 写入 raw_storage_fee
            raw_fee = RawStorageFee(
                country_id=country_obj.id,
                store_id=store_obj.id if store_obj else None,
                asin=asin,
                fnsku=str(get_col(row, "fnsku", "FNSKU") or "").strip(),
                product_name=str(get_col(row, "product_name") or "").strip(),
                fulfillment_center=str(get_col(row, "fulfillment_center") or "").strip(),
                country_code=str(get_col(row, "country_code") or "").strip(),
                longest_side=_safe_decimal(get_col(row, "longest_side")),
                median_side=_safe_decimal(get_col(row, "median_side")),
                shortest_side=_safe_decimal(get_col(row, "shortest_side")),
                measurement_units=str(get_col(row, "measurement_units") or "").strip(),
                weight=_safe_decimal(get_col(row, "weight")),
                weight_units=str(get_col(row, "weight_units") or "").strip(),
                item_volume=_safe_decimal(get_col(row, "item_volume")),
                volume_units=str(get_col(row, "volume_units") or "").strip(),
                product_size_tier=str(get_col(row, "product_size_tier") or "").strip(),
                average_quantity_on_hand=_safe_decimal(get_col(row, "average_quantity_on_hand")),
                average_quantity_pending_removal=_safe_decimal(get_col(row, "average_quantity_pending_removal")),
                estimated_total_item_volume=_safe_decimal(get_col(row, "estimated_total_item_volume")),
                month_of_charge=month_str,
                storage_utilization_ratio=_safe_decimal(get_col(row, "storage_utilization_ratio")),
                storage_utilization_ratio_units=str(get_col(row, "storage_utilization_ratio_units") or "").strip(),
                base_rate=_safe_decimal(get_col(row, "base_rate")),
                utilization_surcharge_rate=_safe_decimal(get_col(row, "utilization_surcharge_rate")),
                avg_qty_for_sus=_safe_decimal(get_col(row, "avg_qty_for_sus")),
                est_vol_for_sus=_safe_decimal(get_col(row, "est_vol_for_sus")),
                est_base_msf=_safe_decimal(get_col(row, "est_base_msf")),
                est_sus=_safe_decimal(get_col(row, "est_sus")),
                currency=str(get_col(row, "currency") or "").strip(),
                estimated_monthly_storage_fee=fee,
                dangerous_goods_storage_type=str(get_col(row, "dangerous_goods_storage_type") or "").strip(),
                eligible_for_inventory_discount=str(get_col(row, "eligible_for_inventory_discount") or "").strip(),
                qualifies_for_inventory_discount=str(get_col(row, "qualifies_for_inventory_discount") or "").strip(),
                total_incentive_fee_amount=_safe_decimal(get_col(row, "total_incentive_fee_amount")),
                breakdown_incentive_fee_amount=_safe_decimal(get_col(row, "breakdown_incentive_fee_amount")),
                average_quantity_customer_orders=_safe_decimal(get_col(row, "average_quantity_customer_orders")),
                raw_data=dict(row),
            )
            db.add(raw_fee)

            key = (asin, month_str)
            if key not in asin_fees:
                asin_fees[key] = Decimal("0")
            asin_fees[key] += fee
            row_count += 1

        summary_count = 0

        for (asin, month_str), total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            # 解析月份并找到对应的 DimTime（支持 Apr-26 / 2026-05 等多种格式）
            time_obj_for_rate = None
            if month_str:
                time_obj_for_rate = _find_time_by_month_str(db, month_str)
                if time_obj_for_rate:
                    filters = [
                        MonthlySummary.product_id == product.id,
                        MonthlySummary.country_id == country_obj.id,
                        MonthlySummary.time_id == time_obj_for_rate.id,
                    ]
                    if store_obj:
                        filters.append(MonthlySummary.store_id == store_obj.id)
                    summary = db.query(MonthlySummary).filter(*filters).first()
                    if not summary:
                        summary = MonthlySummary(
                            country_id=country_obj.id, product_id=product.id, time_id=time_obj_for_rate.id,
                            store_id=store_obj.id if store_obj else None,
                            order_count=0, order_qty=0,
                            product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                            ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                        )
                        db.add(summary)
                    target_summaries = [summary]
                else:
                    target_summaries = []
            else:
                filters = [MonthlySummary.product_id == product.id, MonthlySummary.country_id == country_obj.id]
                if store_obj:
                    filters.append(MonthlySummary.store_id == store_obj.id)
                target_summaries = db.query(MonthlySummary).filter(*filters).all()

            # 按月份获取汇率
            ym_parts = None
            if time_obj_for_rate:
                ym_parts = time_obj_for_rate.year_month.split("-")
            exchange_rate = _get_exchange_rate(db, country_obj, int(ym_parts[0]) if ym_parts else None, int(ym_parts[1]) if ym_parts else None)

            for summary in target_summaries:
                summary.storage_fee_usd = total_fee

                # 重新计算净利润
                net = (
                    summary.product_sales_rmb
                    + Decimal(str(summary.commission_usd or 0)) * exchange_rate
                    + Decimal(str(summary.fba_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.product_cost_rmb or 0))
                    - Decimal(str(summary.freight_cost_rmb or 0))
                    - Decimal(str(summary.ad_spend_usd or 0)) * exchange_rate
                    - total_fee * exchange_rate
                    - Decimal(str(summary.returns_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.inbound_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_tax_usd or 0)) * exchange_rate
    

                ).quantize(Decimal("0.01"))

                summary.net_profit_rmb = net
                if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                    summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))
                summary_count += 1

                summary.net_profit_rmb = net
                if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                    summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

                summary_count += 1

        db.commit()

        return {
            "message": "仓储费导入成功",
            "csv_rows": row_count,
            "summary_updated": summary_count,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /returns: 导入退货费 CSV
# ============================================================
@router.post("/returns")
async def import_returns(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}
        store_obj = _get_or_default_store(db, store)

        content = await file.read()
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件"}

        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames

        def get_col(row, *names):
            for name in names:
                if name in row:
                    return row[name]
            return None

        # 按 ASIN 汇总 + 写 raw_returns
        asin_fees = {}
        row_count = 0

        for row in reader:
            if not row:
                continue

            asin = None
            for key in ["asin", "ASIN", "fnsku", "FNSKU"]:
                val = get_col(row, key)
                if val:
                    asin = str(val).strip()
                    break

            if not asin:
                continue

            fee = _safe_decimal(get_col(row, "sku_returns_fee", "returns_fee", "退货费"))

            # 写入 raw_returns
            raw_ret = RawReturns(
                country_id=country_obj.id,
                store_id=store_obj.id if store_obj else None,
                asin=asin,
                asin_fee_category=str(get_col(row, "asin_fee_category") or "").strip(),
                fnsku=str(get_col(row, "fnsku", "FNSKU") or "").strip(),
                product_name=str(get_col(row, "product_name") or "").strip(),
                longest_side=_safe_decimal(get_col(row, "longest_side")),
                median_side=_safe_decimal(get_col(row, "median_side")),
                shortest_side=_safe_decimal(get_col(row, "shortest_side")),
                measurement_units=str(get_col(row, "measurement-units", "measurement_units") or "").strip(),
                unit_weight=_safe_decimal(get_col(row, "unit_weight")),
                dimensional_weight=_safe_decimal(get_col(row, "dimensional_weight")),
                shipping_weight=_safe_decimal(get_col(row, "shipping_weight")),
                weight_units=str(get_col(row, "weight_units") or "").strip(),
                sku_sizetier=str(get_col(row, "sku_sizetier") or "").strip(),
                month_of_shipment=str(get_col(row, "month_of_shipment") or "").strip(),
                asin_shipped_units=_safe_int(get_col(row, "asin_shipped_units")),
                asin_return_threshold_percent=_safe_decimal(get_col(row, "asin_return_threshold_percent")),
                asin_return_threshold_units=_safe_int(get_col(row, "asin_return_threshold_units")),
                asin_returned_units=_safe_int(get_col(row, "asin_returned_units")),
                sku_returned_units_nsp_exempted=_safe_int(get_col(row, "sku_returned_units_NSP_exempted")),
                sku_returned_units_charged=_safe_int(get_col(row, "sku_returned_units_charged")),
                sku_fee_per_unit=_safe_decimal(get_col(row, "sku_fee_per_unit")),
                sku_returns_fee=fee,
                month_of_charge=str(get_col(row, "month_of_charge") or "").strip(),
                currency=str(get_col(row, "currency") or "").strip(),
                raw_data=dict(row),
            )
            db.add(raw_ret)

            if asin not in asin_fees:
                asin_fees[asin] = Decimal("0")
            asin_fees[asin] += fee
            row_count += 1

        summary_count = 0

        for asin, total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            filters = [MonthlySummary.product_id == product.id, MonthlySummary.country_id == country_obj.id]
            if store_obj:
                filters.append(MonthlySummary.store_id == store_obj.id)
            summaries = (
                db.query(MonthlySummary)
                .filter(*filters)
                .all()
            )

            for summary in summaries:
                summary.returns_fee_usd = total_fee

                # 按月份获取汇率
                time_obj = db.query(DimTime).filter(DimTime.id == summary.time_id).first()
                ym = time_obj.year_month.split("-") if time_obj and time_obj.year_month else None
                exchange_rate = _get_exchange_rate(db, country_obj, int(ym[0]) if ym else None, int(ym[1]) if ym else None)

                net = (
                    summary.product_sales_rmb
                    + Decimal(str(summary.commission_usd or 0)) * exchange_rate
                    + Decimal(str(summary.fba_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.product_cost_rmb or 0))
                    - Decimal(str(summary.freight_cost_rmb or 0))
                    - Decimal(str(summary.ad_spend_usd or 0)) * exchange_rate
                    - Decimal(str(summary.storage_fee_usd or 0)) * exchange_rate
                    - total_fee * exchange_rate
                    - Decimal(str(summary.inbound_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_tax_usd or 0)) * exchange_rate
    

                ).quantize(Decimal("0.01"))

                summary.net_profit_rmb = net
                if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                    summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

                summary_count += 1

        db.commit()

        return {
            "message": "退货费导入成功",
            "csv_rows": row_count,
            "summary_updated": summary_count,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /inbound: 导入入库费 CSV
# ============================================================
@router.post("/inbound")
async def import_inbound(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}
        store_obj = _get_or_default_store(db, store)

        content = await file.read()
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件"}

        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames

        def get_col(row, *names):
            for name in names:
                if name in row:
                    return row[name]
            return None

        # 按 ASIN 汇总 + 写 raw_inbound
        asin_fees = {}
        row_count = 0

        for row in reader:
            if not row:
                continue

            asin = None
            for key in ["asin", "ASIN", "fnsku", "FNSKU"]:
                val = get_col(row, key)
                if val:
                    asin = str(val).strip()
                    break

            if not asin:
                continue

            fee = _safe_decimal(
                get_col(
                    row,
                    "亚马逊物流入库配置服务费用总计",
                    "inbound_fee",
                    "入库费",
                    "fba_inbound_placement_fee",
                )
            )

            # 写入 raw_inbound
            txn_date_str = str(get_col(row, "交易日期") or "").strip()
            txn_date_val = _detect_date_format(txn_date_str) if txn_date_str else None

            raw_inb = RawInbound(
                country_id=country_obj.id,
                store_id=store_obj.id if store_obj else None,
                transaction_date=txn_date_val,
                inbound_plan_id=str(get_col(row, "入库计划编号") or "").strip(),
                fba_shipment_id=str(get_col(row, "亚马逊物流货件编号") or "").strip(),
                country_region=str(get_col(row, "国家/地区") or "").strip(),
                fnsku=str(get_col(row, "FNSKU", "fnsku") or "").strip(),
                asin=asin,
                planned_inbound_service=str(get_col(row, "计划的亚马逊物流入库配置服务") or "").strip(),
                planned_shipment_qty=_safe_int(get_col(row, "计划货件数量")),
                eligible_shipment_qty=_safe_int(get_col(row, "符合要求的货件数量")),
                inbound_defect_type=str(get_col(row, "入库缺陷类型") or "").strip(),
                actual_fee_segment=str(get_col(row, "实际费用分段") or "").strip(),
                planned_inbound_region=str(get_col(row, "计划入库区域") or "").strip(),
                actual_inbound_region=str(get_col(row, "实际入库区域") or "").strip(),
                actual_received_qty=_safe_int(get_col(row, "实际接收数量")),
                product_size_segment=str(get_col(row, "商品尺寸分段") or "").strip(),
                shipping_weight=_safe_decimal(get_col(row, "发货重量")),
                weight_unit=str(get_col(row, "重量单位") or "").strip(),
                inbound_placement_fee_rate=_safe_decimal(get_col(row, "亚马逊物流入库配置服务费率（按商品）")),
                eligible_actual_incentive=_safe_decimal(get_col(row, "符合条件的实际奖励额")),
                currency=str(get_col(row, "货币") or "").strip(),
                inbound_placement_fee_total=fee,
                total_fee=_safe_decimal(get_col(row, "总费用")),
                raw_data=dict(row),
            )
            db.add(raw_inb)

            if asin not in asin_fees:
                asin_fees[asin] = Decimal("0")
            asin_fees[asin] += fee
            row_count += 1

        summary_count = 0

        for asin, total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            filters = [MonthlySummary.product_id == product.id, MonthlySummary.country_id == country_obj.id]
            if store_obj:
                filters.append(MonthlySummary.store_id == store_obj.id)
            summaries = (
                db.query(MonthlySummary)
                .filter(*filters)
                .all()
            )

            for summary in summaries:
                summary.inbound_fee_usd = total_fee

                # 按月份获取汇率
                time_obj = db.query(DimTime).filter(DimTime.id == summary.time_id).first()
                ym = time_obj.year_month.split("-") if time_obj and time_obj.year_month else None
                exchange_rate = _get_exchange_rate(db, country_obj, int(ym[0]) if ym else None, int(ym[1]) if ym else None)

                net = (
                    summary.product_sales_rmb
                    + Decimal(str(summary.commission_usd or 0)) * exchange_rate
                    + Decimal(str(summary.fba_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.product_cost_rmb or 0))
                    - Decimal(str(summary.freight_cost_rmb or 0))
                    - Decimal(str(summary.ad_spend_usd or 0)) * exchange_rate
                    - Decimal(str(summary.storage_fee_usd or 0)) * exchange_rate
                    - Decimal(str(summary.returns_fee_usd or 0)) * exchange_rate
                    - total_fee * exchange_rate
                    - Decimal(str(summary.promo_rebate_usd or 0)) * exchange_rate
                    - Decimal(str(summary.promo_rebate_tax_usd or 0)) * exchange_rate
    

                ).quantize(Decimal("0.01"))

                summary.net_profit_rmb = net
                if summary.product_sales_rmb and summary.product_sales_rmb != 0:
                    summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))

                summary_count += 1

        db.commit()

        return {
            "message": "入库费导入成功",
            "csv_rows": row_count,
            "summary_updated": summary_count,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /long-term-storage: 导入长期仓储费 CSV
# ============================================================
@router.post("/long-term-storage")
async def import_long_term_storage(
    file: UploadFile = File(...),
    country: str = Form(..., description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    db: Session = Depends(get_db),
):
    try:
        country = country.upper()
        country_obj = db.query(DimCountry).filter(DimCountry.code == country).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}
        store_obj = _get_or_default_store(db, store)

        content = await file.read()
        for encoding in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"detail": "无法解码文件"}

        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames

        row_count = 0

        for row in reader:
            if not row:
                continue

            asin = str(row.get("asin", "") or row.get("ASIN", "")).strip()
            if not asin:
                continue

            raw_lts = RawLongTermStorage(
                country_id=country_obj.id,
                store_id=store_obj.id if store_obj else None,
                snapshot_date=str(row.get("snapshot-date", "") or "").strip(),
                sku=str(row.get("sku", "") or "").strip(),
                fnsku=str(row.get("fnsku", "") or "").strip(),
                asin=asin,
                product_name=str(row.get("product-name", "") or "").strip(),
                condition_val=str(row.get("condition", "") or "").strip(),
                per_unit_volume=_safe_decimal(row.get("per-unit-volume")),
                currency=str(row.get("currency", "") or "").strip(),
                volume_unit=str(row.get("volume-unit", "") or "").strip(),
                country=str(row.get("country", "") or "").strip(),
                qty_charged=_safe_int(row.get("qty-charged")),
                amount_charged=_safe_decimal(row.get("amount-charged")),
                surcharge_age_tier=str(row.get("surcharge-age-tier", "") or "").strip(),
                rate_surcharge=_safe_decimal(row.get("rate-surcharge")),
                raw_data=dict(row),
            )
            db.add(raw_lts)
            row_count += 1

        db.commit()

        return {
            "message": "长期仓储费导入成功",
            "csv_rows": row_count,
        }

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


# ============================================================
# POST /workbook: 上传合并工作簿，自动识别所有 sheet
# ============================================================
@router.post("/folder")
async def import_folder(
    files: list[UploadFile] = File(...),
    country: str = Form("auto", description="国家代码，auto=自动检测"),
    store: str = Form(..., description="店铺代码"),
    import_year: int = Form(..., description="导入年份"),
    import_month: int = Form(..., description="导入月份"),
    db: Session = Depends(get_db),
):
    """多文件批量导入，基于内容自动识别类型逐文件处理"""
    store_obj = _get_or_default_store(db, store)
    if not store_obj: return {"detail": f"店铺 {store} 不存在"}
    
    results = []
    for file in files:
        try:
            # Read file content
            content = await file.read()
            file.file.seek(0)
            filename = file.filename
            is_csv = filename.lower().endswith('.csv')
            
            if is_csv:
                for enc in ["utf-8-sig", "latin-1", "gbk", "utf-8"]:
                    try: text = content.decode(enc); break
                    except: continue
                lines = text.splitlines()
                
                # Detect type from header
                headers = []
                file_type = None
                for try_row in [9, 8, 0]:
                    if try_row < len(lines):
                        headers = [h.strip().strip('\"').lower() for h in lines[try_row].split(',')]
                        hs = ' '.join(headers)
                        if any(h in ('date/time','fecha/hora') for h in headers) and 'sku' in headers:
                            file_type = 'transaction'; break
                        if '商品' in hs and ('花费' in hs or 'roas' in hs):
                            file_type = 'advertising'; break
                        if 'asin' in headers and 'estimated_monthly_storage_fee' in hs:
                            file_type = 'storage'; break
                        if 'asin' in hs and 'sku_returns_fee' in hs:
                            file_type = 'returns'; break
                        if 'snapshot-date' in hs and 'amount-charged' in hs:
                            file_type = 'long_term_storage'; break
                        if any('入库' in h for h in headers):
                            file_type = 'inbound'; break
                
                if not file_type:
                    results.append(f'⚠ {filename}: 无法识别类型')
                    continue
                
                # Detect country
                detected = country if country != 'auto' else None
                if not detected and file_type == 'transaction':
                    # Scan marketplace column
                    for line in lines:
                        parts = line.lower().split(',')
                        for p in parts:
                            p = p.strip().strip('\"')
                            if 'amazon.com.mx' in p: detected = 'MX'; break
                            if 'amazon.ca' in p: detected = 'CA'; break
                            if 'amazon.com' in p: detected = 'US'; break
                detected = detected or 'US'
                
                # Find country 
                country_obj = db.query(DimCountry).filter(DimCountry.code == detected).first()
                if not country_obj:
                    results.append(f'⚠ {filename}: 国家 {detected} 不存在'); continue

                # Process via existing standalone import function
                country_obj = db.query(DimCountry).filter(DimCountry.code == detected).first()
                if not country_obj:
                    country_obj = db.query(DimCountry).filter(DimCountry.code == 'US').first()
                
                # Create a temp UploadFile-like object and call existing function
                from starlette.datastructures import UploadFile as UF
                import tempfile, os as _os
                
                # Save content to temp file
                suffix = _os.path.splitext(filename)[1]
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(content)
                tmp.close()
                
                try:
                    # Use existing import functions based on type
                    if file_type == 'transaction':
                        # Use import_transaction's internal logic
                        # For now: note it needs the UI import path
                        results.append(f'✓ {filename}: {file_type}({detected}) 请用单独Tab导入交易数据')
                    elif file_type == 'advertising':
                        reader = csv.reader(io.StringIO(text))
                        rows = list(reader)
                        for r in rows[1:]:
                            if len(r) < 2: continue
                            asin = (r[0] or '').split('-')[0]
                            spend = _safe_decimal(r[10] if len(r)>10 else r[1])
                            db.add(RawAdvertising(country_id=country_obj.id, store_id=store_obj.id, asin=asin, spend_usd=spend))
                        results.append(f'✓ {filename}: {file_type}({detected}) {len(rows)-1}行')
                    else:
                        results.append(f'✓ {filename}: {file_type}({detected}) - 暂不支持')
                finally:
                    _os.unlink(tmp.name)
            
            elif filename.endswith('.xlsx'):
                import openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if not rows: continue
                headers = [str(c).lower().strip() if c else '' for c in rows[0]]
                hs = ' '.join(headers)
                file_type = None
                if 'asin' in headers:
                    if '成本' in hs or 'color' in hs: file_type = 'product_info'
                    elif 'estimated_monthly_storage_fee' in hs or 'fulfillment_center' in hs: file_type = 'storage'
                if file_type:
                    results.append(f'✓ {filename}: {file_type}, {len(rows)}行')
                else:
                    results.append(f'⚠ {filename}: 无法识别')
        
        except Exception as e:
            results.append(f'✗ {filename}: {str(e)[:80]}')
    
    db.commit()
    # 补建 summary + 重算利润（所有涉及的国家）
    detected_countries = set()
    for r in results:
        if isinstance(r, str) and '(' in r and ')' in r:
            cc = r.split('(')[1].split(')')[0]
            if cc in ('US', 'UK', 'DE', 'CA', 'MX'):
                detected_countries.add(cc)
    if not detected_countries:
        detected_countries = {'US'}
    for cc in detected_countries:
        co = db.query(DimCountry).filter(DimCountry.code == cc).first()
        if co:
            _ensure_all_products_have_summary(db, co, store_id=store_obj.id)
            _recalculate_all_profit(db, co)
    db.commit()
    return {"message": f"处理完成，共 {len(results)} 个文件", "countries": list(detected_countries), "files": results}


def _process_csv_file(db, country_obj, store_id, filename, lines, import_year=None, import_month=None):
    """处理单个CSV文件：检测类型并导入"""
    from decimal import Decimal
    from datetime import datetime
    
    # Use proper CSV parsing
    text = ''.join(lines)
    csv_reader = csv.reader(io.StringIO(text))
    all_rows = list(csv_reader)
    
    # Find header row
    header_row = 0
    for i in range(min(15, len(all_rows))):
        lh = [h.strip().strip('\"').lower() for h in all_rows[i]]
        if any(k in lh for k in ['sku', 'asin', '商品', 'date/time', 'fecha/hora']):
            header_row = i; break
    
    headers = [h.strip().strip('\"').lower() for h in all_rows[header_row]]
    data_rows = all_rows[header_row+1:]
    hs = ' '.join(headers)
    
    # === TRANSACTION ===
    if ('date/time' in headers or 'fecha/hora' in headers) and 'sku' in headers:
        # Multi-lang mapping (Spanish → English)
        ml_map = {
            'fecha/hora': 'date/time',
            'id. de liquidación': 'settlement id',
            'tipo': 'type',
            'id. del pedido': 'order id',
            'descripción': 'description',
            'cantidad': 'quantity',
            'cumplimiento': 'fulfillment',
            'ciudad del pedido': 'order city',
            'estado del pedido': 'order state',
            'código postal del pedido': 'order postal',
            'ventas de productos': 'product sales',
            'impuesto de ventas de productos': 'product sales tax',
            'créditos de envío': 'shipping credits',
            'impuesto de abono de envío': 'shipping credits tax',
            'créditos por envoltorio de regalo': 'gift wrap credits',
            'impuesto de créditos de envoltura': 'giftwrap credits tax',
            'tarifa reglamentaria': 'regulatory fee',
            'impuesto sobre tarifa reglamentaria': 'tax on regulatory fee',
            'descuentos promocionales': 'promotional rebates',
            'impuesto de reembolsos promocionales': 'promotional rebates tax',
            'impuesto de retenciones en la plataforma': 'marketplace withheld tax',
            'tarifas de venta': 'selling fees',
            'tarifas fba': 'fba fees',
            'tarifas de otra transacción': 'other transaction fees',
            'otro': 'other',
            'estado de la transacción': 'transaction status',
            'fecha de liberación de la transacción': 'transaction release date',
        }
        mapped_headers = [ml_map.get(h, h) for h in headers]
        
        # Map rows
        rows = []
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            if len(parts) < 5: continue
            row = {mapped_headers[i]: parts[i].strip().strip('\"') for i in range(min(len(mapped_headers), len(parts)))}
            row['_raw_sku'] = row.get('sku','')
            rows.append(row)
        
        # Process
        raw_count = 0
        summary_count = 0
        sku_agg = {}
        adj_agg2 = {}  # Adjustment aggregation for Path 2
        rate = _get_exchange_rate(db, country_obj, import_year, import_month)
        
        for row in rows:
            sku = row.get('sku', '').strip()
            txn_type = row.get('type', '').strip()
            if txn_type.lower() in ('pedido',): txn_type = 'Order'
            elif txn_type.lower() in ('reembolso',): txn_type = 'Refund'
            elif txn_type.lower() in ('ajuste',): txn_type = 'Adjustment'

            # Adjustment 处理
            if txn_type == 'Adjustment':
                adj_key = (effective_sku, year, month)
                if adj_key not in adj_agg2:
                    adj_agg2[adj_key] = {'total': Decimal('0'), 'qty': 0}
                adj_agg2[adj_key]['total'] += _safe_decimal(row.get('total'))
                order_id_val = row.get('order id', '')
                if not order_id_val or not str(order_id_val).strip():
                    adj_agg2[adj_key]['qty'] += (1 if _safe_decimal(row.get('total')) > 0 else -1 if _safe_decimal(row.get('total')) < 0 else 0)
                continue

            if txn_type not in ('Order', 'Refund'): continue
            
            # Parse date
            date_str = row.get('date/time', '')
            txn_date = _detect_date_format(date_str)
            if not txn_date and import_year:
                txn_date = datetime(import_year, import_month, 1)
            
            ps = _safe_decimal(row.get('product sales'))
            sf = _safe_decimal(row.get('selling fees'))
            ff = _safe_decimal(row.get('fba fees'))
            qty = _safe_int(row.get('quantity'))
            ship = _safe_decimal(row.get('shipping credits'))
            promo = _safe_decimal(row.get('promotional rebates'))
            promo_tax = _safe_decimal(row.get('promotional rebates tax'))
            mkt_tax = _safe_decimal(row.get('marketplace withheld tax'))
            gift = _safe_decimal(row.get('gift wrap credits'))
            
            year = import_year if import_year else (txn_date.year if txn_date else 2026)
            month = import_month if import_month else (txn_date.month if txn_date else 1)
            
            raw = RawTransaction(
                country_id=country_obj.id, store_id=store_id,
                transaction_date=txn_date, transaction_type=txn_type,
                sku=sku, description=row.get('description','')[:200],
                quantity=qty, product_sales=ps, selling_fee=sf, fba_fee=ff,
                shipping_credits=ship, promotional_rebates=promo, gift_wrap_credits=gift,
                promotional_rebates_tax=promo_tax, marketplace_withheld_tax=mkt_tax,
            )
            db.add(raw); raw_count += 1

            # amzn.gr handling
            real_sku = _extract_real_sku(sku) if sku.startswith('amzn.gr.') else None
            effective_sku = real_sku or sku
            is_replacement = bool(real_sku)

            key = (effective_sku, year, month)
            if key not in sku_agg:
                sku_agg[key] = {'ps': Decimal('0'), 'sf': Decimal('0'), 'ff': Decimal('0'), 'qty': 0, 'oqty': 0, 'ship': Decimal('0'), 'promo': Decimal('0'), 'promo_tax': Decimal('0'), 'mkt_tax': Decimal('0'), 'gift': Decimal('0')}
            a = sku_agg[key]
            a['ps'] += ps + ship + gift  # 不含 promo
            a['promo'] += promo
            a['promo_tax'] += promo_tax
            a['mkt_tax'] += mkt_tax
            a['sf'] += sf; a['ff'] += ff
            if txn_type == 'Refund': a['qty'] -= abs(qty)
            else:
                a['qty'] += abs(qty)
                if not is_replacement: a['oqty'] += abs(qty)
        
        for (effective_sku, year, month), a in sku_agg.items():
            product = _find_product_by_sku(db, effective_sku)
            if not product:
                asin = effective_sku.split('-')[0] if '-' in effective_sku else effective_sku
                product = _get_or_create_product(db, asin, effective_sku)
            if not product: continue
            
            time_obj = _get_or_create_time(db, year, month)
            ms = db.query(MonthlySummary).filter(
                MonthlySummary.country_id==country_obj.id, MonthlySummary.product_id==product.id,
                MonthlySummary.time_id==time_obj.id, MonthlySummary.store_id==store_id
            ).first()
            if not ms:
                ms = MonthlySummary(country_id=country_obj.id, product_id=product.id, time_id=time_obj.id, store_id=store_id)
                db.add(ms)
            
            ms.product_sales_usd = a['ps']; ms.commission_usd = a['sf']; ms.fba_fee_usd = a['ff']
            ms.promo_rebate_usd = a['promo']; ms.promo_rebate_tax_usd = a['promo_tax']; ms.marketplace_withheld_tax_usd = a['mkt_tax']
            ms.order_count = a['qty']; ms.order_qty = a['oqty']
            ms.exchange_rate = rate
            ms.product_sales_rmb = (a['ps'] * rate).quantize(Decimal('0.01'))
            
            # Costs from dim_product_cost
            ym_str = f'{year}-{month:02d}'
            pc = db.query(DimProductCost).filter(DimProductCost.product_id==product.id, DimProductCost.year_month==ym_str).first()
            if not pc: pc = db.query(DimProductCost).filter(DimProductCost.product_id==product.id).first()
            unit_cost = Decimal(str(pc.cost_rmb if pc else 0)); unit_freight = Decimal(str(pc.freight_per_unit if pc else 0))
            ms.product_cost_rmb = (unit_cost * a['oqty']).quantize(Decimal('0.01'))
            ms.freight_cost_rmb = (unit_freight * a['oqty']).quantize(Decimal('0.01'))
            summary_count += 1

        # 处理 Adjustment
        for (adj_sku, adj_year, adj_month), adj in adj_agg2.items():
            product = _find_product_by_sku(db, adj_sku)
            if not product:
                asin = adj_sku.split('-')[0] if '-' in adj_sku else adj_sku
                product = _get_or_create_product(db, asin, adj_sku)
            if not product: continue
            time_obj = _get_or_create_time(db, adj_year, adj_month)
            ms = db.query(MonthlySummary).filter(
                MonthlySummary.country_id==country_obj.id, MonthlySummary.product_id==product.id,
                MonthlySummary.time_id==time_obj.id, MonthlySummary.store_id==store_id
            ).first()
            if not ms:
                ms = MonthlySummary(country_id=country_obj.id, product_id=product.id, time_id=time_obj.id, store_id=store_id)
                db.add(ms)
            ms.adjustment_usd = (ms.adjustment_usd or Decimal('0')) + adj['total']
            if adj['qty'] != 0:
                ms.order_qty = (ms.order_qty or 0) + adj['qty']
                ym_str = f'{adj_year}-{adj_month:02d}'
                pc = db.query(DimProductCost).filter(DimProductCost.product_id==product.id, DimProductCost.year_month==ym_str).first()
                if not pc: pc = db.query(DimProductCost).filter(DimProductCost.product_id==product.id).first()
                if pc:
                    ms.product_cost_rmb = (Decimal(str(pc.cost_rmb or 0)) * ms.order_qty).quantize(Decimal('0.01'))
                    ms.freight_cost_rmb = (Decimal(str(pc.freight_per_unit or 0)) * ms.order_qty).quantize(Decimal('0.01'))
            # 重算净利润
            er = rate
            net = (
                Decimal(str(ms.product_sales_rmb or 0))
                + Decimal(str(ms.commission_usd or 0)) * er
                + Decimal(str(ms.fba_fee_usd or 0)) * er
                + Decimal(str(ms.adjustment_usd or 0)) * er
                - Decimal(str(ms.product_cost_rmb or 0))
                - Decimal(str(ms.freight_cost_rmb or 0))
                - Decimal(str(ms.ad_spend_usd or 0)) * er
                - Decimal(str(ms.storage_fee_usd or 0)) * er
                - Decimal(str(ms.returns_fee_usd or 0)) * er
                - Decimal(str(ms.inbound_fee_usd or 0)) * er
            ).quantize(Decimal('0.01'))
            ms.net_profit_rmb = net
            if ms.product_sales_rmb and ms.product_sales_rmb != 0:
                ms.net_profit_rate = (net / ms.product_sales_rmb).quantize(Decimal('0.0001'))
            summary_count += 1

        return f'txn:{raw_count} s:{summary_count}'
    
    # === ADVERTISING ===
    if '商品' in hs and ('花费' in hs or 'roas' in hs):
        ad_count = 0
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            if len(parts) < 5: continue
            headers_dict = {headers[i]: parts[i].strip().strip('\"') for i in range(min(len(headers), len(parts)))}
            asin = (headers_dict.get('商品', '') or '').split('-')[0]
            spend = _safe_decimal(headers_dict.get('花费(usd)', headers_dict.get('花费', '')))
            sales = _safe_decimal(headers_dict.get('销售额(usd)', headers_dict.get('销售额', '')))
            db.add(RawAdvertising(country_id=country_obj.id, store_id=store_id, asin=asin, spend_usd=spend, sales_usd=sales))
            ad_count += 1
        return f'ad:{ad_count}'
    
    # === STORAGE ===
    if 'asin' in headers and 'estimated_monthly_storage_fee' in headers:
        sc = 0
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            if len(parts) < 28: continue
            hd = {headers[i]: parts[i].strip().strip('\"') for i in range(min(len(headers), len(parts)))}
            fee = _safe_decimal(hd.get('estimated_monthly_storage_fee'))
            if fee > 0:
                db.add(RawStorageFee(country_id=country_obj.id, store_id=store_id, asin=hd.get('asin',''), estimated_monthly_storage_fee=fee, month_of_charge=hd.get('month_of_charge','')))
                sc += 1
        return f'storage:{sc}'
    
    # === RETURNS ===
    if 'asin' in headers and 'sku_returns_fee' in headers:
        rc = 0
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            hd = {headers[i]: parts[i].strip().strip('\"') for i in range(min(len(headers), len(parts)))}
            fee = _safe_decimal(hd.get('sku_returns_fee'))
            if fee > 0:
                db.add(RawReturns(country_id=country_obj.id, store_id=store_id, asin=hd.get('asin',''), sku_returns_fee=fee))
                rc += 1
        return f'returns:{rc}'
    
    # === INBOUND ===
    if '入库' in hs or any('inbound' in h for h in headers):
        ic = 0
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            hd = {headers[i]: parts[i].strip().strip('\"') for i in range(min(len(headers), len(parts)))}
            fee = _safe_decimal(hd.get('入库配置服务费用总计', hd.get('inbound_placement_fee_total', hd.get('总费用', ''))))
            if fee > 0:
                db.add(RawInbound(country_id=country_obj.id, store_id=store_id, asin=hd.get('asin',''), inbound_placement_fee_total=fee))
                ic += 1
        return f'inbound:{ic}'
    
    # === LONG TERM ===
    if 'snapshot-date' in hs and 'amount-charged' in hs:
        lc = 0
        for row_list in data_rows:
            if len(row_list) < 5: continue
            parts = row_list
            hd = {headers[i]: parts[i].strip().strip('\"') for i in range(min(len(headers), len(parts)))}
            fee = _safe_decimal(hd.get('amount-charged'))
            if fee > 0:
                db.add(RawLongTermStorage(country_id=country_obj.id, store_id=store_id, asin=hd.get('asin',''), amount_charged=fee))
                lc += 1
        return f'longterm:{lc}'
    
    return 'unknown'


@router.post("/workbook")
async def import_workbook(
    file: UploadFile = File(...),
    country: str = Form("US", description="国家代码"),
    store: str = Form(None, description="店铺代码"),
    import_year: int = Form(None, description="导入年份"),
    import_month: int = Form(None, description="导入月份"),
    db: Session = Depends(get_db),
):
    """上传合并后的工作簿（如 美国站全部数据.xlsx），自动识别每个 sheet 并导入"""
    try:
        import openpyxl

        store_obj = _get_or_default_store(db, store)
        if not store_obj:
            return {"detail": f"店铺 {store} 不存在，请先在系统管理创建"}
        if not store_obj:
            return {"detail": f"店铺 {store} 不存在，请先在系统管理创建"}

        # 清空该店铺的旧数据，避免重复导入
        db.query(RawTransaction).filter(RawTransaction.store_id == store_obj.id).delete()
        db.query(RawAdvertising).filter(RawAdvertising.store_id == store_obj.id).delete()
        db.query(RawStorageFee).filter(RawStorageFee.store_id == store_obj.id).delete()
        db.query(RawReturns).filter(RawReturns.store_id == store_obj.id).delete()
        db.query(RawInbound).filter(RawInbound.store_id == store_obj.id).delete()
        db.query(RawLongTermStorage).filter(RawLongTermStorage.store_id == store_obj.id).delete()
        db.query(MonthlySummary).filter(MonthlySummary.store_id == store_obj.id).delete()
        db.flush()

        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)

        results = {}

        # ===== 识别所有 sheet 类型 =====
        def identify_sheet(header, rows):
            """返回 (sheet_type, header, rows)"""
            if any("date/time" in h or "date / time" in h or "fecha/hora" in h for h in header):
                return "transaction", header, rows
            if len(rows) > 9:
                row10 = [str(h).strip().lower() if h else "" for h in rows[9]]
                if any("date/time" in h or "product sales" in h or "fecha/hora" in h for h in row10):
                    return "transaction", row10, rows[10:]
            header_set = set(h for h in header if h)
            data_rows = rows[1:]
            if "asin" in header_set and any("成本" in h or "cost" in h for h in header):
                return "product_info", header, data_rows
            if any("商品" in h for h in header) and any("花费" in h or "roas" in h for h in header):
                return "advertising", header, data_rows
            if any("returns_fee" in h or "returned_units" in h for h in header):
                return "returns", header, data_rows
            if any("入库" in h or "inbound" in h or "shipped_units" in h for h in header):
                return "inbound", header, data_rows
            if any("estimated_monthly_storage_fee" in h or "estimated_total_item_volume" in h for h in header):
                return "storage", header, data_rows
            if any("amount-charged" in h or "amount_charged" in h for h in header):
                if any("surcharge" in h or "snapshot" in h for h in header):
                    return "long_term_storage", header, data_rows
                return "storage", header, data_rows
            return None, header, data_rows

        # 解析所有 sheet
        sheets = {}  # name -> (type, header, rows)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows or len(all_rows) < 2:
                results[sheet_name] = {"status": "skipped", "reason": "数据不足"}
                continue
            header = [str(h).strip().lower() if h else "" for h in all_rows[0]]
            stype, h, r = identify_sheet(header, all_rows)
            if not stype:
                results[sheet_name] = {"status": "skipped", "reason": "无法识别类型", "headers": header[:5]}
                continue
            sheets[sheet_name] = (stype, h, r)

        # ===== 自动检测国家（每个sheet独立检测，支持多国家工作簿）=====
        # 为每个 sheet 分配国家
        sheet_countries = {}  # sheet_name -> country_code
        for sheet_name, (stype, header, rows) in sheets.items():
            if country and country.upper() != 'AUTO':
                sheet_countries[sheet_name] = country.upper()
            else:
                detected = _detect_country_from_data(db, header, rows)
                if not detected:
                    # 从 sheet 名称推断
                    sn = sheet_name.upper()
                    if 'CA' in sn and 'MX' not in sn: detected = 'CA'
                    elif 'MX' in sn: detected = 'MX'
                    elif 'NA' in sn or 'US' in sn: detected = 'US'
                    else: detected = 'US'  # default
                sheet_countries[sheet_name] = detected

        # 汇总所有涉及的国家
        all_countries = set(sheet_countries.values())
        country_objs = {}
        for cc in all_countries:
            co = db.query(DimCountry).filter(DimCountry.code == cc).first()
            if co:
                country_objs[cc] = co
            else:
                results[f"_country_{cc}"] = {"status": "error", "detail": f"国家 {cc} 不存在于 dim_country"}

        # ===== 第一轮：先产品信息，再交易记录（确保SKU匹配）=====
        product_info_sheets = [(n, h, r) for n, (t, h, r) in sheets.items() if t == "product_info"]
        transaction_sheets = [(n, h, r) for n, (t, h, r) in sheets.items() if t == "transaction"]

        for sheet_name, header, rows in product_info_sheets:
            try:
                result = _process_product_info_sheet(db, header, rows, import_year=import_year, import_month=import_month)
                results[sheet_name] = {"status": "success", "type": "product_info", **result}
            except Exception as e:
                results[sheet_name] = {"status": "error", "type": "product_info", "detail": str(e)}

        for sheet_name, header, rows in transaction_sheets:
            cc = sheet_countries.get(sheet_name, 'US')
            co = country_objs.get(cc)
            if not co:
                results[sheet_name] = {"status": "error", "type": "transaction", "detail": f"国家 {cc} 不存在"}
                continue
            try:
                result = _process_transaction_sheet(db, co, header, rows, store_id=store_obj.id, import_year=import_year, import_month=import_month)
                results[sheet_name] = {"status": "success", "type": "transaction", "country": cc, **result}
            except Exception as e:
                results[sheet_name] = {"status": "error", "type": "transaction", "country": cc, "detail": str(e)}

        db.commit()

        # ===== 补建所有产品的 summary（确保广告/仓储等数据有记录可更新）=====
        for cc, co in country_objs.items():
            _ensure_all_products_have_summary(db, co, store_id=store_obj.id)
        db.commit()

        # ===== 第二轮：广告/退货/入库/仓储（更新已有的 summary）=====
        for sheet_name, (stype, header, rows) in sheets.items():
            if stype in ("product_info", "transaction"):
                continue
            cc = sheet_countries.get(sheet_name, 'US')
            co = country_objs.get(cc)
            if not co:
                results[sheet_name] = {"status": "error", "type": stype, "detail": f"国家 {cc} 不存在"}
                continue
            try:
                if stype == "advertising":
                    result = _process_advertising_sheet(db, co, header, rows, store_id=store_obj.id)
                elif stype == "returns":
                    result = _process_fee_sheet(db, co, header, rows, "returns", store_id=store_obj.id)
                elif stype == "inbound":
                    result = _process_fee_sheet(db, co, header, rows, "inbound", store_id=store_obj.id)
                elif stype == "storage":
                    result = _process_fee_sheet(db, co, header, rows, "storage", store_id=store_obj.id)
                elif stype == "long_term_storage":
                    result = _process_fee_sheet(db, co, header, rows, "long_term_storage", store_id=store_obj.id)
                results[sheet_name] = {"status": "success", "type": stype, "country": cc, **result}
            except Exception as e:
                results[sheet_name] = {"status": "error", "type": stype, "country": cc, "detail": str(e)}

        db.commit()

        # ===== 最后重新计算所有涉及国家的净利润 =====
        for cc, co in country_objs.items():
            _recalculate_all_profit(db, co)
        db.commit()

        # ===== 导入后验证：按国家汇总数据 =====
        country_summary = {}
        for cc, co in country_objs.items():
            stats = db.query(
                func.sum(MonthlySummary.order_count),
                func.sum(MonthlySummary.order_qty),
                func.sum(MonthlySummary.product_sales_usd),
                func.sum(MonthlySummary.ad_spend_usd),
                func.sum(MonthlySummary.storage_fee_usd),
                func.sum(MonthlySummary.net_profit_rmb),
            ).filter(MonthlySummary.country_id == co.id).first()
            raw_orders = db.query(func.count()).filter(
                RawTransaction.country_id == co.id,
                RawTransaction.transaction_type.in_(["Order", "Pedido"]),
            ).scalar()
            raw_refunds = db.query(func.count()).filter(
                RawTransaction.country_id == co.id,
                RawTransaction.transaction_type.in_(["Refund", "Reembolso"]),
            ).scalar()
            country_summary[cc] = {
                "order_count": int(stats[0] or 0),
                "order_qty": int(stats[1] or 0),
                "sales_usd": round(float(stats[2] or 0), 2),
                "ad_spend_usd": round(float(stats[3] or 0), 2),
                "storage_fee_usd": round(float(stats[4] or 0), 2),
                "net_profit_rmb": round(float(stats[5] or 0), 2),
                "raw_orders": raw_orders,
                "raw_refunds": raw_refunds,
            }

        return {"message": "工作簿导入完成", "countries": list(all_countries), "country_summary": country_summary, "sheets": results}

    except Exception as e:
        db.rollback()
        return {"detail": str(e)}


def _find_col(header, *names):
    """在表头中查找列索引（精确匹配优先，避免 "产品" 误匹配 "产品运费/台"）"""
    # 第一轮：精确匹配
    for i, h in enumerate(header):
        for name in names:
            if h == name:
                return i
    # 第二轮：模糊匹配
    for i, h in enumerate(header):
        for name in names:
            if name in h:
                return i
    return None


def _process_transaction_sheet(db, country_obj, header, rows, store_id=None, import_year=None, import_month=None):
    """处理交易记录 sheet，import_year/month 覆盖文件中时间"""
    col_date = _find_col(header, "date/time", "date / time", "fecha/hora")
    col_type = _find_col(header, "type", "tipo")
    col_order = _find_col(header, "order id", "id. del pedido")
    col_sku = _find_col(header, "sku")
    col_desc = _find_col(header, "description", "descripción")
    col_qty = _find_col(header, "quantity", "cantidad")
    col_ps = _find_col(header, "product sales", "ventas de productos")
    col_sf = _find_col(header, "selling fees", "tarifas de venta")
    col_fba = _find_col(header, "fba fees", "tarifas fba")
    col_total = _find_col(header, "total")
    col_marketplace = _find_col(header, "marketplace")
    col_fulfillment = _find_col(header, "fulfillment", "cumplimiento")

    if col_date is None or col_ps is None:
        return {"raw_rows": 0, "summary_rows": 0, "error": "缺少必要列"}

    sku_aggregation = {}
    adj_aggregation3 = {}  # Adjustment aggregation for Path 3
    raw_count = 0
    exchange_rate = _get_exchange_rate(db, country_obj, import_year, import_month)

    # 查找额外列的索引
    col_settlement = _find_col(header, "settlement id", "id. de liquidación")
    col_city = _find_col(header, "order city", "ciudad del pedido")
    col_state = _find_col(header, "order state", "estado del pedido")
    col_postal = _find_col(header, "order postal", "código postal del pedido")
    col_tax_model = _find_col(header, "tax collection model", "modelo de recaudación de impuestos")
    col_ps_tax = _find_col(header, "product sales tax", "impuesto de ventas de productos")
    col_ship_credit = _find_col(header, "shipping credits", "créditos de envío")
    col_ship_credit_tax = _find_col(header, "shipping credits tax", "impuesto de abono de envío")
    col_gift = _find_col(header, "gift wrap credits", "créditos por envoltorio de regalo")
    col_gift_tax = _find_col(header, "giftwrap credits tax", "impuesto de créditos de envoltura")
    col_reg_fee = _find_col(header, "regulatory fee", "tarifa reglamentaria")
    col_reg_tax = _find_col(header, "tax on regulatory fee", "impuesto sobre tarifa reglamentaria")
    col_promo = _find_col(header, "promotional rebates", "descuentos promocionales")
    col_promo_tax = _find_col(header, "promotional rebates tax", "impuesto de reembolsos promocionales")
    col_mkt_tax = _find_col(header, "marketplace withheld tax", "impuesto de retenciones en la plataforma")
    col_other_fee = _find_col(header, "other transaction fees", "tarifas de otra transacción")
    col_other = _find_col(header, "other", "otro")
    col_status = _find_col(header, "status", "transaction status", "estado de la transacción")
    col_release = _find_col(header, "release date", "transaction release date", "fecha de liberación de la transacción")

    for row in rows:
        if not row or len(row) <= col_date:
            continue

        date_val = row[col_date]
        if not date_val:
            continue

        # 解析日期
        if isinstance(date_val, datetime):
            txn_date = date_val
        else:
            txn_date = _detect_date_format(str(date_val))
        if not txn_date:
            continue

        txn_type = str(row[col_type]).strip() if col_type is not None and row[col_type] else ""
        # 西班牙语类型映射
        _type_map = {
            'pedido': 'Order', 'reembolso': 'Refund',
            'order': 'Order', 'refund': 'Refund',
            'ajuste': 'Adjustment', 'adjustment': 'Adjustment',
        }
        txn_type = _type_map.get(txn_type.lower(), txn_type)
        sku = str(row[col_sku]).strip() if col_sku is not None and row[col_sku] else ""
        asin = sku.split("-")[0] if sku and "-" in sku else sku

        # 识别 amzn.gr 替换件，提取真实SKU
        is_replacement = sku.startswith("amzn.gr.") if sku else False
        real_sku = _extract_real_sku(sku) if is_replacement else None
        effective_sku = real_sku if real_sku else sku

        product_sales = _safe_decimal(row[col_ps] if col_ps is not None else 0)
        selling_fee = _safe_decimal(row[col_sf] if col_sf is not None else 0)
        fba_fee = _safe_decimal(row[col_fba] if col_fba is not None else 0)
        quantity = _safe_int(row[col_qty] if col_qty is not None else 0)
        total = _safe_decimal(row[col_total] if col_total is not None else 0)

        # 所有类型都写 raw_transactions
        raw = RawTransaction(
            country_id=country_obj.id,
            store_id=store_id,
            transaction_date=txn_date,
            settlement_id=str(row[col_settlement]).strip() if col_settlement is not None and row[col_settlement] else "",
            transaction_type=txn_type,
            order_id=str(row[col_order]).strip() if col_order is not None and row[col_order] else "",
            sku=sku,
            description=str(row[col_desc]).strip() if col_desc is not None and row[col_desc] else "",
            quantity=quantity,
            marketplace=str(row[col_marketplace]).strip() if col_marketplace is not None and row[col_marketplace] else "",
            fulfillment=str(row[col_fulfillment]).strip() if col_fulfillment is not None and row[col_fulfillment] else "",
            order_city=str(row[col_city]).strip() if col_city is not None and row[col_city] else "",
            order_state=str(row[col_state]).strip() if col_state is not None and row[col_state] else "",
            order_postal=str(row[col_postal]).strip() if col_postal is not None and row[col_postal] else "",
            tax_collection_model=str(row[col_tax_model]).strip() if col_tax_model is not None and row[col_tax_model] else "",
            product_sales=product_sales,
            product_sales_tax=_safe_decimal(row[col_ps_tax] if col_ps_tax is not None else 0),
            shipping_credits=_safe_decimal(row[col_ship_credit] if col_ship_credit is not None else 0),
            shipping_credits_tax=_safe_decimal(row[col_ship_credit_tax] if col_ship_credit_tax is not None else 0),
            gift_wrap_credits=_safe_decimal(row[col_gift] if col_gift is not None else 0),
            giftwrap_credits_tax=_safe_decimal(row[col_gift_tax] if col_gift_tax is not None else 0),
            regulatory_fee=_safe_decimal(row[col_reg_fee] if col_reg_fee is not None else 0),
            tax_on_regulatory_fee=_safe_decimal(row[col_reg_tax] if col_reg_tax is not None else 0),
            promotional_rebates=_safe_decimal(row[col_promo] if col_promo is not None else 0),
            promotional_rebates_tax=_safe_decimal(row[col_promo_tax] if col_promo_tax is not None else 0),
            marketplace_withheld_tax=_safe_decimal(row[col_mkt_tax] if col_mkt_tax is not None else 0),
            selling_fee=selling_fee,
            fba_fee=fba_fee,
            other_transaction_fee=_safe_decimal(row[col_other_fee] if col_other_fee is not None else 0),
            other_amount=_safe_decimal(row[col_other] if col_other is not None else 0),
            total=total,
            transaction_status=str(row[col_status]).strip() if col_status is not None and row[col_status] else "",
            transaction_release_date=_detect_date_format(str(row[col_release])) if col_release is not None and row[col_release] else None,
        )
        db.add(raw)
        raw_count += 1

        # Adjustment 处理
        if txn_type == "Adjustment":
            year = import_year if import_year else txn_date.year
            month = import_month if import_month else txn_date.month
            adj_key = (effective_sku, year, month)
            if adj_key not in adj_aggregation3:
                adj_aggregation3[adj_key] = {"total": Decimal("0"), "qty": 0}
            adj_aggregation3[adj_key]["total"] += total
            order_id_val = row[col_order] if col_order is not None else ""
            if not order_id_val or not str(order_id_val).strip():
                adj_aggregation3[adj_key]["qty"] += (1 if total > 0 else -1 if total < 0 else 0)
            continue

        # 仅 Order/Refund 参与 monthly_summary 聚合
        if txn_type not in ("Order", "Refund"):
            continue

        year = import_year if import_year else txn_date.year
        month = import_month if import_month else txn_date.month
        key = (effective_sku, year, month)
        if key not in sku_aggregation:
            sku_aggregation[key] = {"product_sales": Decimal("0"), "selling_fee": Decimal("0"), "fba_fee": Decimal("0"), "quantity": 0, "order_qty": 0, "promo_rebate": Decimal("0"), "promo_rebate_tax": Decimal("0"), "marketplace_withheld_tax": Decimal("0")}
        agg = sku_aggregation[key]
        # 总收入 = product_sales + shipping_credits + gift_wrap_credits（不含 promotional_rebates）
        shipping = _safe_decimal(row[col_ship_credit] if col_ship_credit is not None else 0)
        promo = _safe_decimal(row[col_promo] if col_promo is not None else 0)
        promo_tax = _safe_decimal(row[col_promo_tax] if col_promo_tax is not None else 0)
        mkt_tax = _safe_decimal(row[col_mkt_tax] if col_mkt_tax is not None else 0)
        gift = _safe_decimal(row[col_gift] if col_gift is not None else 0)
        total_revenue = product_sales + shipping + gift
        agg["product_sales"] += total_revenue
        agg["promo_rebate"] += promo
        agg["promo_rebate_tax"] += promo_tax
        agg["marketplace_withheld_tax"] += mkt_tax
        agg["selling_fee"] += selling_fee
        agg["fba_fee"] += fba_fee
        # Refund 数量为负（净销量）
        if txn_type == "Refund":
            agg["quantity"] -= abs(quantity)
        else:
            agg["quantity"] += abs(quantity)
            # amzn.gr 替换件不计入 order_qty（不产生采购成本）
            if not is_replacement:
                agg["order_qty"] += abs(quantity)

    # 写 monthly_summary
    summary_count = 0
    for (sku, year, month), agg in sku_aggregation.items():
        # 先通过 SKU 查找已有产品，找不到则用 SKU 前缀作为 ASIN
        product = _find_product_by_sku(db, sku)
        if not product:
            asin = sku.split("-")[0] if sku and "-" in sku else sku
            product = _get_or_create_product(db, asin, sku)
        if not product:
            continue
        time_obj = _get_or_create_time(db, year, month)
        summary = _get_or_create_monthly_summary(db, country_obj.id, product.id, time_obj.id, store_id=store_id)

        summary.product_sales_usd = agg["product_sales"]
        summary.commission_usd = agg["selling_fee"]
        summary.fba_fee_usd = agg["fba_fee"]
        summary.promo_rebate_usd = agg["promo_rebate"]
        summary.promo_rebate_tax_usd = agg["promo_rebate_tax"]
        summary.marketplace_withheld_tax_usd = agg["marketplace_withheld_tax"]
        summary.exchange_rate = exchange_rate
        summary.product_sales_rmb = (agg["product_sales"] * exchange_rate).quantize(Decimal("0.01"))
        summary.order_count = agg["quantity"]  # 净销量用于显示
        summary.order_qty = agg["order_qty"]   # 下单数量（不扣退货）

        # 采购成本和运费从 dim_product_cost 按月取值
        time_obj = db.query(DimTime).filter(DimTime.id == summary.time_id).first()
        ym_str = time_obj.year_month if time_obj else None
        pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id, DimProductCost.year_month == ym_str).first()
        if not pc:
            pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id).first()
        unit_cost = Decimal(str(pc.cost_rmb if pc else 0))
        unit_freight = Decimal(str(pc.freight_per_unit if pc else 0))
        cost_rmb = (unit_cost * agg["order_qty"]).quantize(Decimal("0.01"))
        freight_rmb = (unit_freight * agg["order_qty"]).quantize(Decimal("0.01"))
        summary.product_cost_rmb = cost_rmb
        summary.freight_cost_rmb = freight_rmb
        summary_count += 1

    # 处理 Adjustment
    for (adj_sku, adj_year, adj_month), adj_agg in adj_aggregation3.items():
        product = _find_product_by_sku(db, adj_sku)
        if not product:
            asin = adj_sku.split("-")[0] if adj_sku and "-" in adj_sku else adj_sku
            product = _get_or_create_product(db, asin, adj_sku)
        if not product:
            continue
        time_obj = _get_or_create_time(db, adj_year, adj_month)
        summary = _get_or_create_monthly_summary(db, country_obj.id, product.id, time_obj.id, store_id=store_id)
        summary.adjustment_usd = (summary.adjustment_usd or Decimal("0")) + adj_agg["total"]
        if adj_agg["qty"] != 0:
            summary.order_qty = (summary.order_qty or 0) + adj_agg["qty"]
            pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id, DimProductCost.year_month == f"{adj_year}-{adj_month:02d}").first()
            if not pc:
                pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id).first()
            if pc:
                summary.product_cost_rmb = (Decimal(str(pc.cost_rmb or 0)) * summary.order_qty).quantize(Decimal("0.01"))
                summary.freight_cost_rmb = (Decimal(str(pc.freight_per_unit or 0)) * summary.order_qty).quantize(Decimal("0.01"))
        # 重算净利润
        er = exchange_rate
        net = (
            Decimal(str(summary.product_sales_rmb or 0))
            + Decimal(str(summary.commission_usd or 0)) * er
            + Decimal(str(summary.fba_fee_usd or 0)) * er
            + Decimal(str(summary.adjustment_usd or 0)) * er
            - Decimal(str(summary.product_cost_rmb or 0))
            - Decimal(str(summary.freight_cost_rmb or 0))
            - Decimal(str(summary.ad_spend_usd or 0)) * er
            - Decimal(str(summary.storage_fee_usd or 0)) * er
            - Decimal(str(summary.returns_fee_usd or 0)) * er
            - Decimal(str(summary.inbound_fee_usd or 0)) * er
        ).quantize(Decimal("0.01"))
        summary.net_profit_rmb = net
        if summary.product_sales_rmb and summary.product_sales_rmb != 0:
            summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))
        summary_count += 1

    return {"raw_rows": raw_count, "summary_rows": summary_count}


def _process_product_info_sheet(db, header, rows, import_year=None, import_month=None):
    """处理产品信息 sheet"""
    col_asin = _find_col(header, "asin")
    col_sku = _find_col(header, "sku")
    col_name = _find_col(header, "产品", "product")
    col_color = _find_col(header, "颜色", "color")
    col_cost = _find_col(header, "成本", "cost")
    col_freight = _find_col(header, "运费", "freight")
    col_time = _find_col(header, "时间", "time")

    if col_asin is None:
        return {"rows": 0, "error": "缺少 ASIN 列"}

    count = 0
    for row in rows:
        if not row or not row[col_asin]:
            continue

        asin = str(row[col_asin]).strip()
        sku = str(row[col_sku]).strip() if col_sku is not None and row[col_sku] else None
        name = str(row[col_name]).strip() if col_name is not None and row[col_name] else None
        color = str(row[col_color]).strip() if col_color is not None and row[col_color] else None
        cost = _safe_decimal(row[col_cost]) if col_cost is not None else Decimal("0")
        freight = _safe_decimal(row[col_freight]) if col_freight is not None else Decimal("0")

        product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
        if not product:
            product = DimProduct(asin=asin, sku=sku or asin, product_name=name or "", color=color)
            db.add(product)
            db.flush()
        else:
            if sku: product.sku = sku
            if name: product.product_name = name
            if color: product.color = color
        # 解析时间写 dim_product_cost
        ym = None
        if col_time is not None and row[col_time]:
            import re as _re
            s = str(row[col_time]).strip()[:10]
            if _re.match(r'\d{4}-\d{2}', s):
                ym = s[:7]
        if not ym and import_year and import_month:
            ym = f"{import_year}-{import_month:02d}"
        if ym:
            pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id, DimProductCost.year_month == ym).first()
            if not pc:
                db.add(DimProductCost(product_id=product.id, year_month=ym, cost_rmb=cost, freight_per_unit=freight))
        count += 1

    return {"rows": count}


def _process_advertising_sheet(db, country_obj, header, rows, time_id=None, store_id=None):
    """处理广告 sheet，自动从行的 time 列解析月份，忽略 time_id 参数"""
    col_product = _find_col(header, "商品", "asin")
    col_spend = _find_col(header, "花费(usd)", "花费(cad)", "花费(mx)", "花费")
    col_sales = _find_col(header, "销售额(usd)", "销售额(cad)", "销售额(mx)", "销售额")
    col_time = _find_col(header, "time", "日期", "date")
    col_acos = _find_col(header, "acos")
    col_roas = _find_col(header, "roas")
    col_ctr = _find_col(header, "ctr")
    col_cpc = _find_col(header, "cpc")
    col_imp = _find_col(header, "展示", "impression")
    col_clicks = _find_col(header, "点击", "click")
    col_orders = _find_col(header, "订单", "order")
    col_conv = _find_col(header, "转化", "conversion")
    col_status = _find_col(header, "状态")
    col_type = _find_col(header, "类型")
    col_elig = _find_col(header, "资格")
    col_ntb_orders = _find_col(header, "ntb 订单数量")
    col_ntb_pct = _find_col(header, "ntb 订单数量百分比")
    col_ntb_sales = _find_col(header, "ntb 销售额")
    col_new_brand = _find_col(header, "品牌新客")
    col_vis_imp = _find_col(header, "可见展示")

    if col_product is None:
        return {"csv_rows": 0, "summary_updated": 0, "error": "缺少商品列"}

    ad_agg = {}  # key: (asin, year, month)
    row_count = 0
    import re as _re

    for row in rows:
        if not row or not row[col_product]:
            continue

        product_field = str(row[col_product]).strip()
        asin = product_field.split("-")[0]

        # 解析 time 列
        ad_year, ad_month = None, None
        if col_time is not None and row[col_time]:
            time_str = str(row[col_time]).strip()
            m = _re.search(r'(\d{4})[/\-](\d{1,2})', time_str)
            if m:
                ad_year = int(m.group(1))
                ad_month = int(m.group(2))
            else:
                m = _re.search(r'(\w+)[\-/](\d{2,4})', time_str)
                if m:
                    month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                                 "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                    month_str = m.group(1).lower()[:3]
                    year_str = m.group(2)
                    if month_str in month_map:
                        ad_month = month_map[month_str]
                        ad_year = int(year_str) if len(year_str) == 4 else int("20" + year_str) if len(year_str) == 2 else None

        ad_spend = _safe_decimal(row[col_spend]) if col_spend is not None else Decimal("0")
        ad_sales = _safe_decimal(row[col_sales]) if col_sales is not None else Decimal("0")

        # 写入 raw_advertising
        raw_adv = RawAdvertising(
            country_id=country_obj.id,
            store_id=store_id,
            product_field=product_field,
            asin=asin,
            status_val=str(row[col_status]).strip() if col_status is not None and row[col_status] else "",
            ad_type=str(row[col_type]).strip() if col_type is not None and row[col_type] else "",
            eligibility=str(row[col_elig]).strip() if col_elig is not None and row[col_elig] else "",
            sales_usd=ad_sales,
            roas=_safe_decimal(row[col_roas]) if col_roas is not None else Decimal("0"),
            conversion_rate=_safe_decimal(row[col_conv]) if col_conv is not None else Decimal("0"),
            impressions=_safe_int(row[col_imp]) if col_imp is not None else 0,
            clicks=_safe_int(row[col_clicks]) if col_clicks is not None else 0,
            ctr=_safe_decimal(row[col_ctr]) if col_ctr is not None else Decimal("0"),
            spend_usd=ad_spend,
            cpc=_safe_decimal(row[col_cpc]) if col_cpc is not None else Decimal("0"),
            orders=_safe_int(row[col_orders]) if col_orders is not None else 0,
            acos=_safe_decimal(row[col_acos]) if col_acos is not None else Decimal("0"),
            ntb_orders=_safe_int(row[col_ntb_orders]) if col_ntb_orders is not None else 0,
            ntb_order_pct=_safe_decimal(row[col_ntb_pct]) if col_ntb_pct is not None else Decimal("0"),
            ntb_sales_usd=_safe_decimal(row[col_ntb_sales]) if col_ntb_sales is not None else Decimal("0"),
            new_to_brand_sales_pct=_safe_decimal(row[col_new_brand]) if col_new_brand is not None else Decimal("0"),
            visible_impressions=_safe_int(row[col_vis_imp]) if col_vis_imp is not None else 0,
        )
        db.add(raw_adv)

        # 按月聚合
        ym_key = (asin, ad_year, ad_month) if ad_year and ad_month else (asin, None, None)
        if ym_key not in ad_agg:
            ad_agg[ym_key] = {"ad_spend": Decimal("0"), "ad_sales": Decimal("0"), "acos": [], "roas": [], "ctr": [], "cpc": [], "imp": 0, "clicks": 0, "orders": 0, "conv": []}
        agg = ad_agg[ym_key]
        agg["ad_spend"] += ad_spend
        agg["ad_sales"] += ad_sales
        if col_acos is not None and row[col_acos]: agg["acos"].append(_safe_decimal(row[col_acos]))
        if col_roas is not None and row[col_roas]: agg["roas"].append(_safe_decimal(row[col_roas]))
        if col_ctr is not None and row[col_ctr]: agg["ctr"].append(_safe_decimal(row[col_ctr]))
        if col_cpc is not None and row[col_cpc]: agg["cpc"].append(_safe_decimal(row[col_cpc]))
        if col_imp is not None and row[col_imp]: agg["imp"] += _safe_int(row[col_imp])
        if col_clicks is not None and row[col_clicks]: agg["clicks"] += _safe_int(row[col_clicks])
        if col_orders is not None and row[col_orders]: agg["orders"] += _safe_int(row[col_orders])
        if col_conv is not None and row[col_conv]: agg["conv"].append(_safe_decimal(row[col_conv]))
        row_count += 1

    summary_count = 0

    for (asin, ad_year, ad_month), agg in ad_agg.items():
        product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
        if not product:
            continue

        exchange_rate = _get_exchange_rate(db, country_obj, ad_year, ad_month)

        # 确定目标月份
        if ad_year and ad_month:
            time_obj = _get_or_create_time(db, ad_year, ad_month)
            time_id = time_obj.id
            summary = db.query(MonthlySummary).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == country_obj.id,
                MonthlySummary.time_id == time_id,
            ).first()
            if not summary:
                summary = MonthlySummary(
                    country_id=country_obj.id,
                    product_id=product.id,
                    time_id=time_id,
                    order_count=0, order_qty=0,
                    product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                    ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                )
                db.add(summary)
            target_summaries = [summary]
        else:
            # 无时间信息，更新该国家所有月份（必须加 country_id 过滤！）
            target_summaries = db.query(MonthlySummary).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == country_obj.id,
            ).all()

        for summary in target_summaries:
            summary.ad_spend_usd = agg["ad_spend"]
            summary.ad_sales_usd = agg["ad_sales"]
            summary.acos = (sum(agg["acos"]) / len(agg["acos"])).quantize(Decimal("0.0001")) if agg["acos"] else Decimal("0")
            summary.roas = (sum(agg["roas"]) / len(agg["roas"])).quantize(Decimal("0.0001")) if agg["roas"] else Decimal("0")
            summary.ctr = (sum(agg["ctr"]) / len(agg["ctr"])).quantize(Decimal("0.0001")) if agg["ctr"] else Decimal("0")
            summary.cpc = (sum(agg["cpc"]) / len(agg["cpc"])).quantize(Decimal("0.01")) if agg["cpc"] else Decimal("0")
            summary.impressions = agg["imp"]
            summary.clicks = agg["clicks"]
            summary.ad_orders = agg["orders"]
            summary.conversion_rate = (sum(agg["conv"]) / len(agg["conv"])).quantize(Decimal("0.0001")) if agg["conv"] else Decimal("0")
            summary_count += 1

    return {"csv_rows": row_count, "summary_updated": summary_count}


def _process_fee_sheet(db, country_obj, header, rows, fee_type, store_id=None):
    """处理费用类 sheet（仓储/退货/入库/长期仓储），按行识别国家"""
    col_asin = _find_col(header, "asin")
    col_fee = None

    if fee_type == "storage":
        col_fee = _find_col(header, "estimated_monthly_storage_fee", "amount-charged", "amount_charged", "storage_fee")
    elif fee_type == "returns":
        col_fee = _find_col(header, "sku_returns_fee", "returns_fee")
    elif fee_type == "inbound":
        col_fee = _find_col(header, "入库配置服务费用总计", "inbound_fee", "总费用")
    elif fee_type == "long_term_storage":
        col_fee = _find_col(header, "amount-charged", "amount_charged")

    if col_asin is None or col_fee is None:
        return {"csv_rows": 0, "summary_updated": 0, "error": f"缺少必要列 (asin={col_asin}, fee={col_fee})"}

    # 按行识别国家的列
    col_row_country = _find_col(header, "country_code", "country", "国家/地区")
    # 国家缓存：country_code -> country_obj
    _country_cache = {}
    def _get_row_country(row):
        """从行中读取国家代码，返回 country_obj，默认使用传入的 country_obj"""
        if col_row_country is not None and row[col_row_country]:
            cc = str(row[col_row_country]).strip().upper()
            if cc in _country_cache:
                return _country_cache[cc]
            # 映射：US/USA -> US, CA/CAN -> CA, MX/MEX -> MX
            cc_map = {'US': 'US', 'USA': 'US', 'CA': 'CA', 'CAN': 'CA', 'MX': 'MX', 'MEX': 'MX',
                      'UK': 'UK', 'GB': 'UK', 'DE': 'DE', 'DEU': 'DE'}
            code = cc_map.get(cc, cc)
            co = db.query(DimCountry).filter(DimCountry.code == code).first()
            _country_cache[cc] = co
            if co:
                return co
        return country_obj

    asin_fees = {}  # (country_id, asin, month_str) -> Decimal
    row_count = 0
    col_moc = _find_col(header, "month_of_charge", "交易日期", "snapshot-date")

    for row in rows:
        if not row or not row[col_asin]:
            continue
        asin = str(row[col_asin]).strip()
        if not asin or asin.startswith("Amazon."):
            continue
        fee = _safe_decimal(row[col_fee]) if row[col_fee] else Decimal("0")

        # 按行确定国家
        row_country = _get_row_country(row)

        # 确定月份
        month_str = ""
        if col_moc is not None and row[col_moc]:
            raw_moc = str(row[col_moc]).strip()
            if len(raw_moc) >= 7:
                month_str = raw_moc[:7]

        # 写入对应的 raw 表
        if fee_type == "storage":
            col_fnsku = _find_col(header, "fnsku")
            col_pname = _find_col(header, "product_name")
            col_fc = _find_col(header, "fulfillment_center")
            col_cc = _find_col(header, "country_code")
            col_tier = _find_col(header, "product_size_tier")
            col_moc = _find_col(header, "month_of_charge")
            col_currency = _find_col(header, "currency")

            raw = RawStorageFee(
                country_id=row_country.id,
                store_id=store_id,
                asin=asin,
                fnsku=str(row[col_fnsku]).strip() if col_fnsku is not None and row[col_fnsku] else "",
                product_name=str(row[col_pname]).strip() if col_pname is not None and row[col_pname] else "",
                fulfillment_center=str(row[col_fc]).strip() if col_fc is not None and row[col_fc] else "",
                country_code=str(row[col_cc]).strip() if col_cc is not None and row[col_cc] else "",
                product_size_tier=str(row[col_tier]).strip() if col_tier is not None and row[col_tier] else "",
                month_of_charge=str(row[col_moc]).strip() if col_moc is not None and row[col_moc] else "",
                currency=str(row[col_currency]).strip() if col_currency is not None and row[col_currency] else "",
                estimated_monthly_storage_fee=fee,
            )
            db.add(raw)

        elif fee_type == "returns":
            col_fnsku = _find_col(header, "fnsku")
            col_pname = _find_col(header, "product_name")
            col_cat = _find_col(header, "asin_fee_category")
            col_mos = _find_col(header, "month_of_shipment")
            col_moc = _find_col(header, "month_of_charge")
            col_currency = _find_col(header, "currency")
            col_shipped = _find_col(header, "asin_shipped_units")
            col_ret_units = _find_col(header, "asin_returned_units")
            col_fee_per = _find_col(header, "sku_fee_per_unit")

            raw = RawReturns(
                country_id=row_country.id,
                store_id=store_id,
                asin=asin,
                asin_fee_category=str(row[col_cat]).strip() if col_cat is not None and row[col_cat] else "",
                fnsku=str(row[col_fnsku]).strip() if col_fnsku is not None and row[col_fnsku] else "",
                product_name=str(row[col_pname]).strip() if col_pname is not None and row[col_pname] else "",
                month_of_shipment=str(row[col_mos]).strip() if col_mos is not None and row[col_mos] else "",
                asin_shipped_units=_safe_int(row[col_shipped]) if col_shipped is not None else 0,
                asin_returned_units=_safe_int(row[col_ret_units]) if col_ret_units is not None else 0,
                sku_fee_per_unit=_safe_decimal(row[col_fee_per]) if col_fee_per is not None else Decimal("0"),
                sku_returns_fee=fee,
                month_of_charge=str(row[col_moc]).strip() if col_moc is not None and row[col_moc] else "",
                currency=str(row[col_currency]).strip() if col_currency is not None and row[col_currency] else "",
            )
            db.add(raw)

        elif fee_type == "inbound":
            col_fnsku = _find_col(header, "fnsku", "FNSKU")
            col_date = _find_col(header, "交易日期")
            col_plan = _find_col(header, "入库计划编号")
            col_shipment = _find_col(header, "亚马逊物流货件编号")
            col_country = _find_col(header, "国家/地区")
            col_currency = _find_col(header, "货币")
            col_total = _find_col(header, "总费用")

            txn_date_str = str(row[col_date]).strip() if col_date is not None and row[col_date] else ""
            txn_date_val = _detect_date_format(txn_date_str) if txn_date_str else None

            raw = RawInbound(
                country_id=row_country.id,
                store_id=store_id,
                transaction_date=txn_date_val,
                inbound_plan_id=str(row[col_plan]).strip() if col_plan is not None and row[col_plan] else "",
                fba_shipment_id=str(row[col_shipment]).strip() if col_shipment is not None and row[col_shipment] else "",
                country_region=str(row[col_country]).strip() if col_country is not None and row[col_country] else "",
                fnsku=str(row[col_fnsku]).strip() if col_fnsku is not None and row[col_fnsku] else "",
                asin=asin,
                inbound_placement_fee_total=fee,
                currency=str(row[col_currency]).strip() if col_currency is not None and row[col_currency] else "",
                total_fee=_safe_decimal(row[col_total]) if col_total is not None else Decimal("0"),
            )
            db.add(raw)

        elif fee_type == "long_term_storage":
            col_sku = _find_col(header, "sku")
            col_fnsku = _find_col(header, "fnsku")
            col_pname = _find_col(header, "product-name", "product_name")
            col_snap = _find_col(header, "snapshot-date", "snapshot_date")
            col_cond = _find_col(header, "condition")
            col_currency = _find_col(header, "currency")
            col_vol = _find_col(header, "per-unit-volume")
            col_qty = _find_col(header, "qty-charged")
            col_tier = _find_col(header, "surcharge-age-tier")
            col_rate = _find_col(header, "rate-surcharge")

            raw = RawLongTermStorage(
                country_id=row_country.id,
                store_id=store_id,
                snapshot_date=str(row[col_snap]).strip() if col_snap is not None and row[col_snap] else "",
                sku=str(row[col_sku]).strip() if col_sku is not None and row[col_sku] else "",
                fnsku=str(row[col_fnsku]).strip() if col_fnsku is not None and row[col_fnsku] else "",
                asin=asin,
                product_name=str(row[col_pname]).strip() if col_pname is not None and row[col_pname] else "",
                condition_val=str(row[col_cond]).strip() if col_cond is not None and row[col_cond] else "",
                per_unit_volume=_safe_decimal(row[col_vol]) if col_vol is not None else Decimal("0"),
                currency=str(row[col_currency]).strip() if col_currency is not None and row[col_currency] else "",
                qty_charged=_safe_int(row[col_qty]) if col_qty is not None else 0,
                amount_charged=fee,
                surcharge_age_tier=str(row[col_tier]).strip() if col_tier is not None and row[col_tier] else "",
                rate_surcharge=_safe_decimal(row[col_rate]) if col_rate is not None else Decimal("0"),
            )
            db.add(raw)

        key = (row_country.id, asin, month_str)
        if key not in asin_fees:
            asin_fees[key] = Decimal("0")
        asin_fees[key] += fee
        row_count += 1

    summary_count = 0

    for (fee_country_id, asin, month_str), total_fee in asin_fees.items():
        product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
        if not product:
            continue

        # 查找对应月份的 summary（支持 Apr-26 / 2026-05 等多种格式）
        time_obj = None
        if month_str:
            time_obj = _find_time_by_month_str(db, month_str)

        if time_obj:
            summary = db.query(MonthlySummary).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == fee_country_id,
                MonthlySummary.time_id == time_obj.id,
            ).first()
            if not summary:
                summary = MonthlySummary(
                    country_id=fee_country_id, product_id=product.id, time_id=time_obj.id,
                    order_count=0, order_qty=0,
                    product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                    ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                )
                db.add(summary)
            target_summaries = [summary]
        else:
            # 没有月份信息，更新该国家所有月份
            target_summaries = db.query(MonthlySummary).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == fee_country_id,
            ).all()

        for summary in target_summaries:
            if fee_type == "storage" or fee_type == "long_term_storage":
                summary.storage_fee_usd = total_fee
            elif fee_type == "returns":
                summary.returns_fee_usd = total_fee
            elif fee_type == "inbound":
                summary.inbound_fee_usd = total_fee
            summary_count += 1

    return {"csv_rows": row_count, "summary_updated": summary_count}


def _ensure_all_products_have_summary(db, country_obj, store_id=None):
    """为有实际原始数据的产品补建缺失月份的 monthly_summary 记录"""
    all_times = db.query(DimTime).all()
    if not all_times:
        return
    all_products = db.query(DimProduct).filter(
        DimProduct.asin.notlike("Amazon.%")
    ).all()
    for product in all_products:
        # 只为有实际交易/广告/仓储等原始数据的产品创建记录
        has_data = db.query(RawTransaction.id).filter(
            RawTransaction.country_id == country_obj.id,
            RawTransaction.sku == product.sku,
        ).first()
        if not has_data:
            has_data = db.query(RawAdvertising.id).filter(
                RawAdvertising.country_id == country_obj.id,
                RawAdvertising.asin == product.asin,
            ).first()
        if not has_data:
            continue
        # 获取已有记录的月份ID集合
        existing_ids = set(
            r[0] for r in db.query(MonthlySummary.time_id).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == country_obj.id,
            ).all()
        )
        # 为缺失的月份补建记录
        for time_obj in all_times:
            if time_obj.id in existing_ids:
                continue
            summary = MonthlySummary(
                country_id=country_obj.id,
                product_id=product.id,
                time_id=time_obj.id,
                store_id=store_id,
                order_count=0,
                order_qty=0,
                product_sales_usd=Decimal("0"),
                commission_usd=Decimal("0"),
                fba_fee_usd=Decimal("0"),
                ad_spend_usd=Decimal("0"),
                storage_fee_usd=Decimal("0"),
                returns_fee_usd=Decimal("0"),
                inbound_fee_usd=Decimal("0"),
            )
            db.add(summary)
    db.flush()


def _recalculate_all_profit(db, country_obj):
    """重新计算该国家所有 monthly_summary 的净利润（不覆盖 order_count/order_qty）"""
    from sqlalchemy import text

    # 用原生 SQL 补充计算 order_qty（仅当 order_qty=0 且有 Order 数据时）
    # 注意：不覆盖已有的 order_qty，因为聚合逻辑已排除了替换件
    db.execute(text("""
        UPDATE monthly_summary ms
        JOIN dim_product dp ON dp.id = ms.product_id
        JOIN dim_time dt ON dt.id = ms.time_id
        SET ms.order_qty = (
            SELECT COALESCE(SUM(ABS(rt.quantity)), 0)
            FROM raw_transactions rt
            WHERE rt.transaction_type = 'Order'
              AND rt.country_id = :country_id
              AND rt.sku = dp.sku
              AND YEAR(rt.transaction_date) = dt.time_year
              AND MONTH(rt.transaction_date) = dt.time_month
        )
        WHERE ms.country_id = :country_id
          AND (ms.order_qty IS NULL OR ms.order_qty = 0)
    """), {"country_id": country_obj.id})

    # 用 ORM 重算成本和利润（不覆盖 order_count）
    summaries = (
        db.query(MonthlySummary)
        .filter(MonthlySummary.country_id == country_obj.id)
        .all()
    )

    for summary in summaries:
        product = db.query(DimProduct).filter(DimProduct.id == summary.product_id).first()
        if not product:
            continue

        # 获取对应月份的时间
        time_obj = db.query(DimTime).filter(DimTime.id == summary.time_id).first()
        ym = time_obj.year_month if time_obj else None

        order_qty = summary.order_qty or summary.order_count or 0
        summary.order_qty = order_qty

        # 按月份查找成本（优先当月，否则取任意有成本的记录）
        cost_per_unit = Decimal("0")
        freight_per_unit = Decimal("0")
        if ym:
            pc = db.query(DimProductCost).filter(
                DimProductCost.product_id == product.id,
                DimProductCost.year_month == ym
            ).first()
            if pc:
                cost_per_unit = Decimal(str(pc.cost_rmb or 0))
                freight_per_unit = Decimal(str(pc.freight_per_unit or 0))
        if cost_per_unit == 0:
            # fallback: 取第一条成本记录
            pc = db.query(DimProductCost).filter(DimProductCost.product_id == product.id).first()
            if pc:
                cost_per_unit = Decimal(str(pc.cost_rmb or 0))
                freight_per_unit = Decimal(str(pc.freight_per_unit or 0))
        # 按月度汇率换算
        er = Decimal(str(db.query(DimExchangeRate).filter(
            DimExchangeRate.country_id == country_obj.id, DimExchangeRate.year_month == ym).first().rate or 6.8
        )) if db.query(DimExchangeRate).filter(DimExchangeRate.country_id == country_obj.id, DimExchangeRate.year_month == ym).first() else Decimal("6.8")
        if er == Decimal("0"): er = Decimal("6.8")

        summary.product_cost_rmb = (cost_per_unit * order_qty).quantize(Decimal("0.01"))
        summary.freight_cost_rmb = (freight_per_unit * order_qty).quantize(Decimal("0.01"))
        summary.exchange_rate = er
        summary.product_sales_rmb = (Decimal(str(summary.product_sales_usd or 0)) * er).quantize(Decimal("0.01"))
        summary.amazon_payout_usd = (
            Decimal(str(summary.product_sales_usd or 0))
            + Decimal(str(summary.commission_usd or 0))
            + Decimal(str(summary.fba_fee_usd or 0))
        ).quantize(Decimal("0.01"))

        net = (
            summary.product_sales_rmb
            + Decimal(str(summary.commission_usd or 0)) * er
            + Decimal(str(summary.fba_fee_usd or 0)) * er
            + Decimal(str(summary.adjustment_usd or 0)) * er
            - summary.product_cost_rmb
            - summary.freight_cost_rmb
            - Decimal(str(summary.ad_spend_usd or 0)) * er
            - Decimal(str(summary.storage_fee_usd or 0)) * er
            - Decimal(str(summary.returns_fee_usd or 0)) * er
            - Decimal(str(summary.inbound_fee_usd or 0)) * er
        ).quantize(Decimal("0.01"))

        summary.net_profit_rmb = net
        if summary.product_sales_rmb and summary.product_sales_rmb != 0:
            summary.net_profit_rate = (net / summary.product_sales_rmb).quantize(Decimal("0.0001"))


# ============================================================
# GET /supported: 返回支持的导入类型
# ============================================================
@router.get("/supported")
def get_supported_imports():
    return {
        "supported_types": [
            {
                "type": "transaction",
                "name": "交易记录",
                "endpoint": "/api/import/transaction",
                "method": "POST",
                "file_type": "CSV",
                "description": "Amazon Transaction Report，前9行元数据跳过，第10行表头",
                "params": ["country"],
            },
            {
                "type": "product-info",
                "name": "产品信息",
                "endpoint": "/api/import/product-info",
                "method": "POST",
                "file_type": "XLSX",
                "description": "产品信息表，列：ASIN, SKU, 产品, 颜色, 成本RMB, 产品运费/台, 汇率",
                "params": [],
            },
            {
                "type": "advertising",
                "name": "广告数据",
                "endpoint": "/api/import/advertising",
                "method": "POST",
                "file_type": "CSV",
                "description": "广告报告，列：商品, 花费(USD), 销售额(USD), ROAS, CTR, CPC, ACOS 等",
                "params": ["country"],
            },
            {
                "type": "storage",
                "name": "仓储费",
                "endpoint": "/api/import/storage",
                "method": "POST",
                "file_type": "CSV",
                "description": "FBA Inventory Storage 报告，按 ASIN 汇总 estimated_monthly_storage_fee",
                "params": ["country"],
            },
            {
                "type": "returns",
                "name": "退货费",
                "endpoint": "/api/import/returns",
                "method": "POST",
                "file_type": "CSV",
                "description": "退货报告，按 ASIN 汇总 sku_returns_fee",
                "params": ["country"],
            },
            {
                "type": "inbound",
                "name": "入库费",
                "endpoint": "/api/import/inbound",
                "method": "POST",
                "file_type": "CSV",
                "description": "入库配置费报告，按 ASIN 汇总入库配置服务费用总计",
                "params": ["country"],
            },
            {
                "type": "long-term-storage",
                "name": "长期仓储费",
                "endpoint": "/api/import/long-term-storage",
                "method": "POST",
                "file_type": "CSV",
                "description": "长期仓储费报告，按 ASIN 存储 amount-charged、surcharge-age-tier 等",
                "params": ["country"],
            },
        ]
    }


# ============================================================
# GET /validate: 导入后验证数据一致性
# ============================================================
@router.get("/validate")
def validate_import(db: Session = Depends(get_db)):
    """验证导入数据的一致性：按国家汇总并与原始数据对比"""
    try:
        countries = db.query(DimCountry).all()
        report = {}

        for co in countries:
            # summary 汇总
            stats = db.query(
                func.sum(MonthlySummary.order_count),
                func.sum(MonthlySummary.order_qty),
                func.sum(MonthlySummary.product_sales_usd),
                func.sum(MonthlySummary.ad_spend_usd),
                func.sum(MonthlySummary.storage_fee_usd),
                func.sum(MonthlySummary.returns_fee_usd),
                func.sum(MonthlySummary.inbound_fee_usd),
                func.sum(MonthlySummary.net_profit_rmb),
                func.count(),
            ).filter(MonthlySummary.country_id == co.id).first()

            # raw 交易统计
            raw_order_count = db.query(func.count()).filter(
                RawTransaction.country_id == co.id,
                RawTransaction.transaction_type.in_(["Order", "Pedido"]),
            ).scalar()
            raw_order_qty = db.query(func.sum(RawTransaction.quantity)).filter(
                RawTransaction.country_id == co.id,
                RawTransaction.transaction_type.in_(["Order", "Pedido"]),
            ).scalar() or 0
            raw_refund_qty = db.query(func.sum(func.abs(RawTransaction.quantity))).filter(
                RawTransaction.country_id == co.id,
                RawTransaction.transaction_type.in_(["Refund", "Reembolso"]),
            ).scalar() or 0

            # raw 广告
            raw_ad_spend = db.query(func.sum(RawAdvertising.spend_usd)).filter(
                RawAdvertising.country_id == co.id
            ).scalar() or 0

            # raw 仓储
            raw_storage = db.query(func.sum(RawStorageFee.estimated_monthly_storage_fee)).filter(
                RawStorageFee.country_id == co.id
            ).scalar() or 0

            summary_oc = int(stats[0] or 0)
            expected_oc = int(raw_order_qty) - int(raw_refund_qty)

            report[co.code] = {
                "summary": {
                    "order_count": summary_oc,
                    "order_qty": int(stats[1] or 0),
                    "sales_usd": round(float(stats[2] or 0), 2),
                    "ad_spend_usd": round(float(stats[3] or 0), 2),
                    "storage_fee_usd": round(float(stats[4] or 0), 2),
                    "returns_fee_usd": round(float(stats[5] or 0), 2),
                    "inbound_fee_usd": round(float(stats[6] or 0), 2),
                    "net_profit_rmb": round(float(stats[7] or 0), 2),
                    "product_count": stats[8],
                },
                "raw": {
                    "order_rows": raw_order_count,
                    "order_qty": int(raw_order_qty),
                    "refund_qty": int(raw_refund_qty),
                    "expected_order_count": expected_oc,
                    "ad_spend": round(float(raw_ad_spend), 2),
                    "storage_fee": round(float(raw_storage), 2),
                },
                "checks": {
                    "order_count_match": abs(summary_oc - expected_oc) <= 15,  # 允许15单误差(amzn.gr)
                    "order_count_diff": summary_oc - expected_oc,
                    "has_data": summary_oc > 0,
                },
            }

        return {"report": report}

    except Exception as e:
        return {"detail": str(e)}
