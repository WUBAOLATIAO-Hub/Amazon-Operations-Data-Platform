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
    """从数据文件中自动检测国家: marketplace/country_code → US/UK/DE"""
    mp_idx = None; cc_idx = None
    for i, h in enumerate(header):
        hl = h.lower() if h else ""
        if 'marketplace' in hl: mp_idx = i
        if 'country_code' in hl or h == 'country': cc_idx = i
    for row in rows[:10]:
        vals = []
        if mp_idx is not None and len(row) > mp_idx: vals.append(str(row[mp_idx] or '').lower())
        if cc_idx is not None and len(row) > cc_idx: vals.append(str(row[cc_idx] or '').lower())
        for v in vals:
            if v in ('us', 'usa', 'amazon.com', 'united states'): return 'US'
            if v in ('uk', 'gb', 'gbr', 'amazon.co.uk', 'united kingdom'): return 'UK'
            if v in ('de', 'deu', 'amazon.de', 'germany'): return 'DE'
    return None


def _get_or_default_store(db: Session, store: str = None):
    """获取店铺对象，未指定返回 None，不存在也返回 None"""
    if not store:
        return None
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
    if not asin or asin.startswith("Amazon."):
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
    """从 amzn.gr.XX-XXXX-XXXX-xxx-x 中提取真实SKU (XX-XXXX-XXXX)"""
    if sku and sku.startswith("amzn.gr."):
        import re as _re
        # amzn.gr.WH-O0WE-F4CW-fkUFJmAenNF5IeG1-LN
        # → parts: ['amzn.gr.WH', 'O0WE', 'F4CW', ...]
        # → 真实SKU: WH-O0WE-F4CW (parts[0]最后一段 + parts[1] + parts[2])
        parts = sku.split("-")
        if len(parts) >= 3:
            prefix = parts[0].split(".")[-1]  # 'amzn.gr.WH' → 'WH'
            candidate = f"{prefix}-{parts[1]}-{parts[2]}"
            if _re.match(r'^[A-Z0-9]{2}-[A-Z0-9]{4}-[A-Z0-9]{4}$', candidate.upper()):
                return candidate
    return None


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
    summary = (
        db.query(MonthlySummary)
        .filter(
            MonthlySummary.country_id == country_id,
            MonthlySummary.product_id == product_id,
            MonthlySummary.time_id == time_id,
        )
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
    # 移除时区后缀 (PDT, PST, EST, etc.)
    date_str_clean = re.sub(r'\s+[A-Z]{2,4}$', '', date_str)
    formats = [
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y %I:%M:%S %p",  # May 1, 2026 5:46:45 AM
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y",
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
        store_obj = _get_or_default_store(db, country_obj, store)

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
        data_lines = lines[10:]

        reader = csv.DictReader(io.StringIO(header_line + "\n" + "\n".join(data_lines)))
        headers = reader.fieldnames
        if not headers:
            return {"detail": "无法解析 CSV 表头"}

        # 字段映射（去空格、小写化）
        def map_header(h):
            h = h.strip().lower()
            mapping = {
                "date/time": "transaction_date",
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
                }
            agg = sku_aggregation[key]
            # 总收入 = product_sales + shipping_credits + promotional_rebates + gift_wrap_credits
            shipping = _safe_decimal(mapped.get("shipping_credits"))
            promo = _safe_decimal(mapped.get("promotional_rebates"))
            gift = _safe_decimal(mapped.get("gift_wrap_credits"))
            agg["product_sales"] += product_sales + shipping + promo + gift
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
        exchange_rate = Decimal("6.8")
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

            summary = _get_or_create_monthly_summary(db, country_obj.id, product.id, time_obj.id)
            summary.store_id = store_obj.id

            summary.product_sales_usd = agg["product_sales"]
            summary.commission_usd = agg["selling_fee"]
            summary.fba_fee_usd = agg["fba_fee"]
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
        store_obj = _get_or_default_store(db, country_obj, store)

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

            ad_spend = _safe_decimal(get_col(row, "花费(USD)", "花费"))
            ad_sales = _safe_decimal(get_col(row, "销售额(USD)", "销售额"))
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
        exchange_rate = Decimal("6.8")
        summary_count = 0

        for (asin, ad_year, ad_month), agg in ad_aggregation.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

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
                target_summaries = db.query(MonthlySummary).filter(MonthlySummary.product_id == product.id).all()
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

        exchange_rate = Decimal("6.8")
        summary_count = 0

        for (asin, month_str), total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            # 解析月份并找到对应的 DimTime（支持 Apr-26 / 2026-05 等多种格式）
            if month_str:
                time_obj = _find_time_by_month_str(db, month_str)
                if time_obj:
                    summary = db.query(MonthlySummary).filter(
                        MonthlySummary.product_id == product.id,
                        MonthlySummary.country_id == country_obj.id,
                        MonthlySummary.time_id == time_obj.id,
                    ).first()
                    if not summary:
                        summary = MonthlySummary(
                            country_id=country_obj.id, product_id=product.id, time_id=time_obj.id,
                            order_count=0, order_qty=0,
                            product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                            ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                        )
                        db.add(summary)
                    target_summaries = [summary]
                else:
                    target_summaries = []
            else:
                target_summaries = db.query(MonthlySummary).filter(MonthlySummary.product_id == product.id).all()

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

        exchange_rate = Decimal("6.8")
        summary_count = 0

        for asin, total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            summaries = (
                db.query(MonthlySummary)
                .filter(MonthlySummary.product_id == product.id)
                .all()
            )

            for summary in summaries:
                summary.returns_fee_usd = total_fee

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

        exchange_rate = Decimal("6.8")
        summary_count = 0

        for asin, total_fee in asin_fees.items():
            product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
            if not product:
                continue

            summaries = (
                db.query(MonthlySummary)
                .filter(MonthlySummary.product_id == product.id)
                .all()
            )

            for summary in summaries:
                summary.inbound_fee_usd = total_fee

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
            if any("date/time" in h or "date / time" in h for h in header):
                return "transaction", header, rows
            if len(rows) > 9:
                row10 = [str(h).strip().lower() if h else "" for h in rows[9]]
                if any("date/time" in h or "product sales" in h for h in row10):
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

        # 自动检测国家
        if not country or country.upper() == 'AUTO':
            country = 'US'  # default
            for sn, (stype, header, rows) in sheets.items():
                c = _detect_country_from_data(db, header, rows)
                if c: country = c; break
        country_obj = db.query(DimCountry).filter(DimCountry.code == country.upper()).first()
        if not country_obj:
            return {"detail": f"国家 {country} 不存在"}

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
            try:
                result = _process_transaction_sheet(db, country_obj, header, rows, store_id=store_obj.id, import_year=import_year, import_month=import_month)
                results[sheet_name] = {"status": "success", "type": "transaction", **result}
            except Exception as e:
                results[sheet_name] = {"status": "error", "type": "transaction", "detail": str(e)}

        db.commit()

        # ===== 补建所有产品的 summary（确保广告/仓储等数据有记录可更新）=====
        _ensure_all_products_have_summary(db, country_obj, store_id=store_obj.id)
        db.commit()

        # ===== 第二轮：广告/退货/入库/仓储（更新已有的 summary）=====
        # 广告数据由 _process_advertising_sheet 自动从行级 time 列解析月份
        for sheet_name, (stype, header, rows) in sheets.items():
            if stype in ("product_info", "transaction"):
                continue
            try:
                if stype == "advertising":
                    result = _process_advertising_sheet(db, country_obj, header, rows, store_id=store_obj.id)
                elif stype == "returns":
                    result = _process_fee_sheet(db, country_obj, header, rows, "returns", store_id=store_obj.id)
                elif stype == "inbound":
                    result = _process_fee_sheet(db, country_obj, header, rows, "inbound", store_id=store_obj.id)
                elif stype == "storage":
                    result = _process_fee_sheet(db, country_obj, header, rows, "storage", store_id=store_obj.id)
                elif stype == "long_term_storage":
                    result = _process_fee_sheet(db, country_obj, header, rows, "long_term_storage", store_id=store_obj.id)
                results[sheet_name] = {"status": "success", "type": stype, **result}
            except Exception as e:
                results[sheet_name] = {"status": "error", "type": stype, "detail": str(e)}

        db.commit()

        # ===== 最后重新计算所有净利润 =====
        _recalculate_all_profit(db, country_obj)
        db.commit()

        return {"message": "工作簿导入完成", "country": country, "sheets": results}

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
    col_date = _find_col(header, "date/time", "date / time")
    col_type = _find_col(header, "type")
    col_order = _find_col(header, "order id")
    col_sku = _find_col(header, "sku")
    col_desc = _find_col(header, "description")
    col_qty = _find_col(header, "quantity")
    col_ps = _find_col(header, "product sales")
    col_sf = _find_col(header, "selling fees")
    col_fba = _find_col(header, "fba fees")
    col_total = _find_col(header, "total")
    col_marketplace = _find_col(header, "marketplace")
    col_fulfillment = _find_col(header, "fulfillment")

    if col_date is None or col_ps is None:
        return {"raw_rows": 0, "summary_rows": 0, "error": "缺少必要列"}

    sku_aggregation = {}
    raw_count = 0
    exchange_rate = Decimal("6.8")

    # 查找额外列的索引
    col_settlement = _find_col(header, "settlement id")
    col_city = _find_col(header, "order city")
    col_state = _find_col(header, "order state")
    col_postal = _find_col(header, "order postal")
    col_tax_model = _find_col(header, "tax collection model")
    col_ps_tax = _find_col(header, "product sales tax")
    col_ship_credit = _find_col(header, "shipping credits")
    col_ship_credit_tax = _find_col(header, "shipping credits tax")
    col_gift = _find_col(header, "gift wrap credits")
    col_gift_tax = _find_col(header, "giftwrap credits tax")
    col_reg_fee = _find_col(header, "regulatory fee")
    col_reg_tax = _find_col(header, "tax on regulatory fee")
    col_promo = _find_col(header, "promotional rebates")
    col_promo_tax = _find_col(header, "promotional rebates tax")
    col_mkt_tax = _find_col(header, "marketplace withheld tax")
    col_other_fee = _find_col(header, "other transaction fees")
    col_other = _find_col(header, "other")
    col_status = _find_col(header, "status", "transaction status")
    col_release = _find_col(header, "release date", "transaction release date")

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

        # 仅 Order/Refund 参与 monthly_summary 聚合
        if txn_type not in ("Order", "Refund"):
            continue

        year = import_year if import_year else txn_date.year
        month = import_month if import_month else txn_date.month
        key = (effective_sku, year, month)
        if key not in sku_aggregation:
            sku_aggregation[key] = {"product_sales": Decimal("0"), "selling_fee": Decimal("0"), "fba_fee": Decimal("0"), "quantity": 0, "order_qty": 0}
        agg = sku_aggregation[key]
        # 总收入 = product_sales + shipping_credits + promotional_rebates + gift_wrap_credits
        shipping = _safe_decimal(row[col_ship_credit] if col_ship_credit is not None else 0)
        promo = _safe_decimal(row[col_promo] if col_promo is not None else 0)
        gift = _safe_decimal(row[col_gift] if col_gift is not None else 0)
        total_revenue = product_sales + shipping + promo + gift
        agg["product_sales"] += total_revenue
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
    col_spend = _find_col(header, "花费")
    col_sales = _find_col(header, "销售额")
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

    exchange_rate = Decimal("6.8")
    summary_count = 0

    for (asin, ad_year, ad_month), agg in ad_agg.items():
        product = db.query(DimProduct).filter(DimProduct.asin == asin).first()
        if not product:
            continue

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
            # 无时间信息，更新所有月份（兼容旧逻辑）
            target_summaries = db.query(MonthlySummary).filter(MonthlySummary.product_id == product.id).all()

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
    """处理费用类 sheet（仓储/退货/入库/长期仓储）"""
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

    asin_fees = {}  # (asin, month_str) -> Decimal
    row_count = 0
    col_moc = _find_col(header, "month_of_charge", "交易日期", "snapshot-date")

    for row in rows:
        if not row or not row[col_asin]:
            continue
        asin = str(row[col_asin]).strip()
        if not asin or asin.startswith("Amazon."):
            continue
        fee = _safe_decimal(row[col_fee]) if row[col_fee] else Decimal("0")

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
                country_id=country_obj.id,
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
                country_id=country_obj.id,
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
                country_id=country_obj.id,
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
                country_id=country_obj.id,
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

        # 查找对应月份的 summary（支持 Apr-26 / 2026-05 等多种格式）
        time_obj = None
        if month_str:
            time_obj = _find_time_by_month_str(db, month_str)

        if time_obj:
            summary = db.query(MonthlySummary).filter(
                MonthlySummary.product_id == product.id,
                MonthlySummary.country_id == country_obj.id,
                MonthlySummary.time_id == time_obj.id,
            ).first()
            if not summary:
                # 创建该月份的 summary
                summary = MonthlySummary(
                    country_id=country_obj.id, product_id=product.id, time_id=time_obj.id,
                    order_count=0, order_qty=0,
                    product_sales_usd=Decimal("0"), commission_usd=Decimal("0"), fba_fee_usd=Decimal("0"),
                    ad_spend_usd=Decimal("0"), storage_fee_usd=Decimal("0"), returns_fee_usd=Decimal("0"), inbound_fee_usd=Decimal("0"),
                )
                db.add(summary)
            target_summaries = [summary]
        else:
            # 没有月份信息，更新所有
            target_summaries = db.query(MonthlySummary).filter(MonthlySummary.product_id == product.id).all()

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
    """为有成本的产品补建缺失月份的 monthly_summary 记录"""
    all_times = db.query(DimTime).all()
    if not all_times:
        return
    all_products = db.query(DimProduct).filter(
        DimProduct.asin.notlike("Amazon.%")
    ).all()
    for product in all_products:
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
    """重新计算该国家所有 monthly_summary 的净利润"""
    from sqlalchemy import text

    # 先用原生 SQL 更新 order_qty（从 raw_transactions 计算下单数量）
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
    """), {"country_id": country_obj.id})

    # 然后用 ORM 重算成本和利润
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
