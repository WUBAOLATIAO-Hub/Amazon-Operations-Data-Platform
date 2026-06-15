#!/usr/bin/env python3
"""
MGK-EU 店铺数据导入脚本
支持：销售明细、产品信息+运费、广告数据、仓储费、超龄仓储费、退回处理费
"""
import os
import sys
import pandas as pd
import mysql.connector
from datetime import datetime
from decimal import Decimal

# ============================================================
# 配置
# ============================================================
DATA_DIR = r"C:\Users\yummy\Desktop\MGK-EU"
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "lmg_platform",
    "charset": "utf8mb4",
}

STORE_CODE = "MGK-EU"

# ============================================================
# 国家配置：代码 → (文件名, header行数, 数字格式类型)
# ============================================================
COUNTRY_CONFIG = {
    "UK": {"file": "MGK-英国站销售明细.csv",   "header": 9,  "numfmt": "dot"},
    "DE": {"file": "MGK-德国站销售明细.csv",   "header": 9,  "numfmt": "comma"},
    "FR": {"file": "MGK-法国站销售明细.csv",   "header": 9,  "numfmt": "comma"},
    "ES": {"file": "MGK-西班牙站销售明细.csv", "header": 9,  "numfmt": "comma"},
    "IT": {"file": "MGK-意大利站销售明细.csv", "header": 9,  "numfmt": "comma"},
    "NL": {"file": "MGK-荷兰站销售明细.csv",   "header": 9,  "numfmt": "comma"},
    "SE": {"file": "MGK-瑞典站销售明细.csv",   "header": 9,  "numfmt": "space_comma"},
    "BE": {"file": "MGK-比利时站销售明细.csv", "header": 9,  "numfmt": "comma"},
    "IE": {"file": "MGK-爱尔兰站销售明细.csv", "header": 9,  "numfmt": "dot"},
    "AE": {"file": "MGK-阿联酋站销售明细.csv", "header": 8,  "numfmt": "mixed"},
    "SA": {"file": "MGK-沙特站销售明细.csv",   "header": 9,  "numfmt": "dot"},
}

# ============================================================
# 多语言列名映射：各种语言 → 统一英文字段名
# ============================================================
COLUMN_MAP = {
    # 日期
    "date/time": "date_time",
    "Date/Time": "date_time",
    "Datum/Uhrzeit": "date_time",
    "date/heure": "date_time",
    "fecha y hora": "date_time",
    "Data/Ora:": "date_time",
    "datum/tijd": "date_time",
    "datum/tid": "date_time",
    # 结算ID
    "settlement id": "settlement_id",
    "settlement ID": "settlement_id",
    "Abrechnungsnummer": "settlement_id",
    "numéro de versement": "settlement_id",
    "identificador de pago": "settlement_id",
    "Numero pagamento": "settlement_id",
    "schikkings-ID": "settlement_id",
    "reglerings-id": "settlement_id",
    "Identifiant du paiement": "settlement_id",
    # 类型
    "type": "type",
    "Typ": "type",
    "tipo": "type",
    "Tipo": "type",
    "typ": "type",
    # 订单号
    "order id": "order_id",
    "order ID": "order_id",
    "Bestellnummer": "order_id",
    "numéro de la commande": "order_id",
    "número de pedido": "order_id",
    "Numero ordine": "order_id",
    "bestelnummer": "order_id",
    "beställnings-id": "order_id",
    "Numéro de la commande": "order_id",
    # SKU
    "sku": "sku",
    "SKU": "sku",
    # 描述
    "description": "description",
    "Beschreibung": "description",
    "descripción": "description",
    "Descrizione": "description",
    "beschrijving": "description",
    "beskrivning": "description",
    # 数量
    "quantity": "quantity",
    "Menge": "quantity",
    "quantité": "quantity",
    "cantidad": "quantity",
    "Quantità": "quantity",
    "aantal": "quantity",
    "antal": "quantity",
    "Quantité": "quantity",
    # marketplace
    "marketplace": "marketplace",
    "Marketplace": "marketplace",
    "web de Amazon": "marketplace",
    "marknadsplats": "marketplace",
    "site de vente": "marketplace",
    # 物流
    "fulfilment": "fulfillment",
    "fulfillment": "fulfillment",
    "Versand": "fulfillment",
    "traitement": "fulfillment",
    "gestión logística": "fulfillment",
    "Gestione": "fulfillment",
    "leverans": "fulfillment",
    "expédition": "fulfillment",
    # 城市
    "order city": "order_city",
    "Ort der Bestellung": "order_city",
    "ville d'où provient la commande": "order_city",
    "ciudad de procedencia del pedido": "order_city",
    "Città di provenienza dell'ordine": "order_city",
    "bestelling stad": "order_city",
    "stad för beställning": "order_city",
    "ville de la commande": "order_city",
    # 州/省
    "order state": "order_state",
    "Bundesland": "order_state",
    "Région d'où provient la commande": "order_state",
    "comunidad autónoma de procedencia del pedido": "order_state",
    "Provincia di provenienza dell'ordine": "order_state",
    "status bestelling": "order_state",
    "delstat för beställning": "order_state",
    "état de la commande": "order_state",
    # 邮编
    "order postal": "order_postal",
    "Postleitzahl": "order_postal",
    "code postal de la commande": "order_postal",
    "código postal de procedencia del pedido": "order_postal",
    "CAP dell'ordine": "order_postal",
    "bestelling per post": "order_postal",
    "postadress för beställning": "order_postal",
    "commande postale": "order_postal",
    # 税收模型（仅29列组有）
    "tax collection model": "tax_collection_model",
    "Steuererhebungsmodell": "tax_collection_model",
    "Modèle de perception des taxes": "tax_collection_model",
    "Formulario de recaudación de impuestos": "tax_collection_model",
    "modello di riscossione delle imposte": "tax_collection_model",
    # 商品销售额
    "product sales": "product_sales",
    "Umsätze": "product_sales",
    "ventes de produits": "product_sales",
    "ventas de productos": "product_sales",
    "Vendite": "product_sales",
    "verkoop van producten": "product_sales",
    "försäljning av produkter": "product_sales",
    "ventes de produits ": "product_sales",
    # 商品销售税（仅29列组有）
    "product sales tax": "product_sales_tax",
    "Produktumsatzsteuer": "product_sales_tax",
    "Taxes sur la vente des produits": "product_sales_tax",
    "impuesto de ventas de productos": "product_sales_tax",
    "imposta sulle vendite dei prodotti": "product_sales_tax",
    # 邮费信用 / 运费信用
    "postage credits": "shipping_credits",
    "shipping credits": "shipping_credits",
    "Gutschrift für Versandkosten": "shipping_credits",
    "crédits d'expédition": "shipping_credits",
    "abonos de envío": "shipping_credits",
    "Accrediti per le spedizioni": "shipping_credits",
    "Verzendtegoeden": "shipping_credits",
    "fraktkrediter": "shipping_credits",
    "crédits d'expédition ": "shipping_credits",
    # 运费信用税（仅UK有）
    "shipping credits tax": "shipping_credits_tax",
    "Steuer auf Versandgutschrift": "shipping_credits_tax",
    "taxe sur les crédits d'expédition": "shipping_credits_tax",
    "impuestos por abonos de envío": "shipping_credits_tax",
    "imposta accrediti per le spedizioni": "shipping_credits_tax",
    # 礼品包装信用
    "gift wrap credits": "gift_wrap_credits",
    "giftwrap credits": "gift_wrap_credits",
    "Gutschrift für Geschenkverpackung": "gift_wrap_credits",
    "crédits sur l'emballage cadeau": "gift_wrap_credits",
    "abonos de envoltorio para regalo": "gift_wrap_credits",
    "Accrediti per confezioni regalo": "gift_wrap_credits",
    "kredietpunten cadeauverpakking": "gift_wrap_credits",
    "krediter för presentinslagning": "gift_wrap_credits",
    "crédits d'emballage-cadeau": "gift_wrap_credits",
    # 礼品包装信用税（仅UK有）
    "giftwrap credits tax": "gift_wrap_credits_tax",
    "Steuer auf Geschenkverpackungsgutschriften": "gift_wrap_credits_tax",
    "Taxes sur les crédits cadeaux": "gift_wrap_credits_tax",
    "impuestos por abonos de envoltorio para regalo": "gift_wrap_credits_tax",
    "imposta sui crediti confezione regalo": "gift_wrap_credits_tax",
    # 促销折扣
    "promotional rebates": "promotional_rebates",
    "Rabatte aus Werbeaktionen": "promotional_rebates",
    "Rabais promotionnels": "promotional_rebates",
    "devoluciones promocionales": "promotional_rebates",
    "Sconti promozionali": "promotional_rebates",
    "promotiekortingen": "promotional_rebates",
    "kampanjrabatter": "promotional_rebates",
    "Total des réductions": "promotional_rebates",
    # 促销折扣税（仅29列组有）
    "promotional rebates tax": "promotional_rebates_tax",
    "Steuer auf Aktionsrabatte": "promotional_rebates_tax",
    "Taxes sur les remises promotionnelles": "promotional_rebates_tax",
    "impuestos de descuentos por promociones": "promotional_rebates_tax",
    "imposta sugli sconti promozionali": "promotional_rebates_tax",
    # marketplace代扣税（仅29列组有）
    "marketplace withheld tax": "marketplace_withheld_tax",
    "Einbehaltene Steuer auf Marketplace": "marketplace_withheld_tax",
    "Taxes retenues sur le site de vente": "marketplace_withheld_tax",
    "impuesto retenido en el sitio web": "marketplace_withheld_tax",
    "trattenuta IVA del marketplace": "marketplace_withheld_tax",
    # 销售佣金
    "selling fees": "selling_fees",
    "Verkaufsgebühren": "selling_fees",
    "frais de vente": "selling_fees",
    "tarifas de venta": "selling_fees",
    "Commissioni di vendita": "selling_fees",
    "verkoopkosten": "selling_fees",
    "försäljningsavgifter": "selling_fees",
    "frais de vente ": "selling_fees",
    # FBA费用
    "fba fees": "fba_fees",
    "FBA fees": "fba_fees",
    "Gebühren zu Versand durch Amazon": "fba_fees",
    "Frais Expédié par Amazon": "fba_fees",
    "tarifas de Logística de Amazon": "fba_fees",
    "Costi del servizio Logistica di Amazon": "fba_fees",
    "fba-vergoedingen": "fba_fees",
    "fba-avgifter": "fba_fees",
    "Frais pour le service Expédié par Amazon": "fba_fees",
    # 其他交易费
    "other transaction fees": "other_transaction_fees",
    "Andere Transaktionsgebühren": "other_transaction_fees",
    "autres frais de transaction": "other_transaction_fees",
    "tarifas de otras transacciones": "other_transaction_fees",
    "Altri costi relativi alle transazioni": "other_transaction_fees",
    "overige transactiekosten": "other_transaction_fees",
    "övriga transaktionsavgifter": "other_transaction_fees",
    # 其他
    "other": "other",
    "Andere": "other",
    "autre": "other",
    "otro": "other",
    "Altro": "other",
    "overige": "other",
    "Övrigt": "other",
    "autres": "other",
    # 总额
    "total": "total",
    "Gesamt": "total",
    "totale": "total",
    "totaal": "total",
    "totalt": "total",
    # 交易状态
    "Transaction status": "transaction_status",
    "Transaction Status": "transaction_status",
    "Transaktionsstatus": "transaction_status",
    "Statut de la transaction": "transaction_status",
    "Estado de la transacción": "transaction_status",
    "Stato della transazione": "transaction_status",
    "Transactiestatus": "transaction_status",
    # 交易释放日期
    "Transaction Release Date": "transaction_release_date",
    "Freigabedatum der Transaktion": "transaction_release_date",
    "Date de sortie de la transaction": "transaction_release_date",
    "Fecha de liberación de la transacción": "transaction_release_date",
    "Data di rilascio della transazione": "transaction_release_date",
    "Publicatiedatum van transactie": "transaction_release_date",
    "Transaktionens utgivningsdatum": "transaction_release_date",
    "Date de délivrance de la transaction": "transaction_release_date",
    # 销售税（25列组有）
    "sales tax collected": "sales_tax_collected",
    "geïnde omzetbelasting": "sales_tax_collected",
    "Inkasserad moms": "sales_tax_collected",
    "taxe de ventes prélevée": "sales_tax_collected",
    "Marketplace Facilitator Tax": "marketplace_facilitator_tax",
    "Marketplace facilitator tax": "marketplace_facilitator_tax",
    "Belasting voor marketplace-facilitator": "marketplace_facilitator_tax",
    "Skatt för marknadsplatsförmedlare": "marketplace_facilitator_tax",
    "Taxe Marketplace Facilitator": "marketplace_facilitator_tax",
}


def parse_number(val, numfmt="dot"):
    """
    解析各种格式的数字字符串
    numfmt: dot(24.99), comma(30,24), space_comma(1 135,72), mixed(1,777.43)
    """
    if pd.isna(val) or val == "" or val is None:
        return Decimal("0")
    s = str(val).strip()
    if not s:
        return Decimal("0")

    if numfmt == "space_comma":
        # 瑞典格式: "1 135,72" → 1135.72
        s = s.replace(" ", "").replace(",", ".")
    elif numfmt == "comma":
        # 欧洲格式: "30,24" → 30.24
        s = s.replace(".", "").replace(",", ".")  # 先去千分位点，再换小数点
    elif numfmt == "mixed":
        # AE格式: "1,777.43" → 逗号是千分位
        s = s.replace(",", "")
    # dot格式直接用

    try:
        return Decimal(s)
    except:
        return Decimal("0")


def normalize_columns(df):
    """将 DataFrame 的列名通过 COLUMN_MAP 映射为统一英文名"""
    new_cols = []
    for col in df.columns:
        col_clean = col.strip()
        mapped = COLUMN_MAP.get(col_clean)
        if mapped:
            new_cols.append(mapped)
        else:
            # 尝试模糊匹配
            found = False
            for k, v in COLUMN_MAP.items():
                if k.lower() == col_clean.lower():
                    new_cols.append(v)
                    found = True
                    break
            if not found:
                new_cols.append(f"_unmapped_{col_clean}")
    df.columns = new_cols
    return df


# ============================================================
# 导入函数
# ============================================================

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_store_id(cursor):
    cursor.execute("SELECT id FROM dim_store WHERE store_code = %s", (STORE_CODE,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_country_id(cursor, code):
    cursor.execute("SELECT id FROM dim_country WHERE code = %s", (code,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_or_create_product(cursor, asin, store_id, sku=None, product_name=None, color=None, cost_rmb=0, weight=0):
    """获取或创建产品记录（店铺隔离），返回 product_id"""
    cursor.execute("SELECT id FROM dim_product WHERE asin = %s AND store_id = %s", (asin, store_id))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO dim_product (asin, store_id, sku, product_name, color, cost_rmb, weight) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (asin, store_id, sku, product_name, color, cost_rmb, weight)
    )
    return cursor.lastrowid


def get_time_id(cursor, year, month):
    ym = f"{year}-{month:02d}"
    cursor.execute("SELECT id FROM dim_time WHERE year_month = %s", (ym,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO dim_time (time_year, time_month, year_month) VALUES (%s,%s,%s)",
        (year, month, ym)
    )
    return cursor.lastrowid


# ============================================================
# 0. 导入汇率
# ============================================================
def import_exchange_rates():
    print("\n=== 导入汇率 ===")
    filepath = os.path.join(DATA_DIR, "汇率.xlsx")
    if not os.path.exists(filepath):
        print("  文件不存在，跳过")
        return

    df = pd.read_excel(filepath)
    conn = get_db()
    cursor = conn.cursor()

    # 默认月份：从销售数据推断（取最早的交易月份）
    # 也可以后续改成从文件读取
    year_month = "2026-05"

    imported = 0
    for _, row in df.iterrows():
        code = str(row["国家"]).strip()
        rate = float(row["汇率"])

        cursor.execute("SELECT id FROM dim_country WHERE code = %s", (code,))
        result = cursor.fetchone()
        if not result:
            print(f"  [{code}] 国家不存在，跳过")
            continue
        country_id = result[0]

        # INSERT OR UPDATE
        cursor.execute("""
            SELECT id FROM dim_exchange_rate
            WHERE country_id = %s AND `year_month` = %s
        """, (country_id, year_month))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE dim_exchange_rate SET rate = %s
                WHERE country_id = %s AND `year_month` = %s
            """, (rate, country_id, year_month))
        else:
            cursor.execute("""
                INSERT INTO dim_exchange_rate (country_id, `year_month`, rate)
                VALUES (%s, %s, %s)
            """, (country_id, year_month, rate))

        imported += 1
        print(f"  [{code}] {rate}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  汇率导入: {imported} 条 ({year_month})")


# ============================================================
# 1. 导入产品信息 + 运费
# ============================================================
def import_products():
    print("\n=== 导入产品信息 + 运费 ===")
    df = pd.read_excel(os.path.join(DATA_DIR, "MGK 欧洲站产品信息表.xlsx"))
    conn = get_db()
    cursor = conn.cursor()

    store_id = get_store_id(cursor)
    uk_id = get_country_id(cursor, "UK")
    ie_id = get_country_id(cursor, "IE")

    # 获取其他欧洲国家ID
    other_country_ids = {}
    for code in ["DE", "FR", "ES", "IT", "NL", "SE", "BE", "AE", "SA"]:
        cid = get_country_id(cursor, code)
        if cid:
            other_country_ids[code] = cid

    imported = 0
    skipped = 0
    for _, row in df.iterrows():
        asin = str(row["ASIN"]).strip()
        sku = str(row["SKU"]).strip()
        # 产品名称：优先"产品"列，fallback到"型号"列
        pn_val = row.get("产品") if "产品" in row.index and pd.notna(row.get("产品")) else (row.get("型号") if "型号" in row.index and pd.notna(row.get("型号")) else None)
        product_name = str(pn_val).strip() if pn_val else None
        color = str(row.get("颜色", "")).strip() if pd.notna(row.get("颜色")) else None
        cost_rmb = float(row["成本RMB"]) if pd.notna(row["成本RMB"]) else 0
        # 运费列名兼容：英国站运费/英国站点运费，爱尔兰站运费/爱尔兰站点运费
        freight_uk_col = "英国站点运费" if "英国站点运费" in row.index else "英国站运费"
        freight_ie_col = "爱尔兰站点运费" if "爱尔兰站点运费" in row.index else "爱尔兰站运费"
        freight_uk = float(row[freight_uk_col]) if freight_uk_col in row.index and pd.notna(row[freight_uk_col]) else 0
        freight_default = float(row["运费"]) if "运费" in row.index and pd.notna(row["运费"]) else 0
        freight_ie = float(row[freight_ie_col]) if freight_ie_col in row.index and pd.notna(row[freight_ie_col]) else 0
        weight = 0  # 产品表没有重量列，后续可补充

        if not asin or asin == "nan":
            skipped += 1
            continue

        # 创建/更新产品（店铺隔离）
        product_id = get_or_create_product(cursor, asin, store_id, sku, product_name, color, cost_rmb, weight)

        # UK 运费（店铺隔离）
        if uk_id and freight_uk > 0:
            cursor.execute("""
                INSERT INTO dim_freight (product_id, country_id, store_id, freight_rmb)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE freight_rmb = VALUES(freight_rmb)
            """, (product_id, uk_id, store_id, freight_uk))

        # IE 运费（店铺隔离）
        if ie_id and freight_ie > 0:
            cursor.execute("""
                INSERT INTO dim_freight (product_id, country_id, store_id, freight_rmb)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE freight_rmb = VALUES(freight_rmb)
            """, (product_id, ie_id, store_id, freight_ie))

        # 其他国家用默认运费（店铺隔离）
        for code, cid in other_country_ids.items():
            if freight_default > 0:
                cursor.execute("""
                    INSERT INTO dim_freight (product_id, country_id, store_id, freight_rmb)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE freight_rmb = VALUES(freight_rmb)
                """, (product_id, cid, store_id, freight_default))

        imported += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  产品导入: {imported} 条, 跳过: {skipped} 条")
    print(f"  运费写入: 每个产品 × {2 + len(other_country_ids)} 个国家")


# ============================================================
# 2. 导入销售明细
# ============================================================
def import_sales():
    print("\n=== 导入销售明细 ===")
    conn = get_db()
    cursor = conn.cursor()
    store_id = get_store_id(cursor)

    total_imported = 0

    for country_code, config in COUNTRY_CONFIG.items():
        filepath = os.path.join(DATA_DIR, config["file"])
        if not os.path.exists(filepath):
            print(f"  [{country_code}] 文件不存在: {config['file']}")
            continue

        country_id = get_country_id(cursor, country_code)
        if not country_id:
            print(f"  [{country_code}] 国家未找到")
            continue

        # 读取CSV，跳过前导行
        df = pd.read_csv(filepath, encoding="utf-8-sig", header=config["header"])

        # 标准化列名
        df = normalize_columns(df)

        # 检查必要字段
        required = ["date_time", "type", "sku", "product_sales", "selling_fees", "fba_fees", "total"]
        missing = [f for f in required if f not in df.columns]
        if missing:
            print(f"  [{country_code}] 缺少字段: {missing}，跳过")
            continue

        numfmt = config["numfmt"]
        imported = 0

        for _, row in df.iterrows():
            # 跳过非交易行（Transfer, Service Fee 等汇总行）
            txn_type = str(row.get("type", "")).strip()
            if txn_type in ("Transfer", ""):
                continue

            # 解析日期
            date_str = str(row.get("date_time", ""))
            txn_date = parse_date(date_str)

            # 解析数值
            product_sales = parse_number(row.get("product_sales", 0), numfmt)
            product_sales_tax = parse_number(row.get("product_sales_tax", 0), numfmt)
            shipping_credits = parse_number(row.get("shipping_credits", 0), numfmt)
            shipping_credits_tax = parse_number(row.get("shipping_credits_tax", 0), numfmt)
            gift_wrap_credits = parse_number(row.get("gift_wrap_credits", 0), numfmt)
            gift_wrap_credits_tax = parse_number(row.get("gift_wrap_credits_tax", 0), numfmt)
            promotional_rebates = parse_number(row.get("promotional_rebates", 0), numfmt)
            promotional_rebates_tax = parse_number(row.get("promotional_rebates_tax", 0), numfmt)
            marketplace_withheld_tax = parse_number(row.get("marketplace_withheld_tax", 0), numfmt)
            selling_fees = parse_number(row.get("selling_fees", 0), numfmt)
            fba_fees = parse_number(row.get("fba_fees", 0), numfmt)
            other_txn_fees = parse_number(row.get("other_transaction_fees", 0), numfmt)
            other_amount = parse_number(row.get("other", 0), numfmt)
            total = parse_number(row.get("total", 0), numfmt)
            quantity = int(parse_number(row.get("quantity", 0), numfmt))

            sku = str(row.get("sku", "")).strip()
            order_id = str(row.get("order_id", "")).strip()
            description = str(row.get("description", "")).strip()
            marketplace_val = str(row.get("marketplace", "")).strip()
            fulfillment_val = str(row.get("fulfillment", "")).strip()
            order_city = str(row.get("order_city", "")).strip()
            order_state = str(row.get("order_state", "")).strip()
            order_postal = str(row.get("order_postal", "")).strip()
            tax_collection_model = str(row.get("tax_collection_model", "")).strip()
            settlement_id = str(row.get("settlement_id", "")).strip()
            txn_status = str(row.get("transaction_status", "")).strip()
            release_date_str = str(row.get("transaction_release_date", ""))
            release_date = parse_date(release_date_str)

            cursor.execute("""
                INSERT INTO raw_transactions (
                    country_id, store_id, transaction_date, settlement_id, transaction_type,
                    order_id, sku, description, quantity, marketplace, fulfillment,
                    order_city, order_state, order_postal, tax_collection_model,
                    product_sales, product_sales_tax, shipping_credits, shipping_credits_tax,
                    gift_wrap_credits, giftwrap_credits_tax,
                    promotional_rebates, promotional_rebates_tax,
                    marketplace_withheld_tax, selling_fee, fba_fee,
                    other_transaction_fee, other_amount, total,
                    transaction_status, transaction_release_date
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
            """, (
                country_id, store_id, txn_date, settlement_id, txn_type,
                order_id, sku, description, quantity, marketplace_val, fulfillment_val,
                order_city, order_state, order_postal, tax_collection_model,
                float(product_sales), float(product_sales_tax),
                float(shipping_credits), float(shipping_credits_tax),
                float(gift_wrap_credits), float(gift_wrap_credits_tax),
                float(promotional_rebates), float(promotional_rebates_tax),
                float(marketplace_withheld_tax), float(selling_fees), float(fba_fees),
                float(other_txn_fees), float(other_amount), float(total),
                txn_status, release_date
            ))
            imported += 1

        conn.commit()
        total_imported += imported
        print(f"  [{country_code}] {imported} 条")

    cursor.close()
    conn.close()
    print(f"  销售明细总计: {total_imported} 条")


def parse_date(date_str):
    """解析各种格式的日期字符串（含法/意/荷/瑞/西/德语月份）"""
    if not date_str or date_str == "nan" or date_str == "NaT":
        return None
    date_str = date_str.strip()

    # 非英语月份名 → 英语月份名
    MONTH_MAP = {
        # 法语
        "janvier": "January", "février": "February", "mars": "March",
        "avril": "April", "mai": "May", "juin": "June",
        "juillet": "July", "août": "August", "septembre": "September",
        "octobre": "October", "novembre": "November", "décembre": "December",
        # 意大利语
        "gennaio": "January", "febbraio": "February", "marzo": "March",
        "aprile": "April", "maggio": "May", "giugno": "June",
        "luglio": "July", "agosto": "August", "settembre": "September",
        "ottobre": "October", "novembre": "November", "dicembre": "December",
        "gen": "Jan", "feb": "Feb", "mag": "May", "giu": "Jun",
        "lug": "Jul", "ago": "Aug", "set": "Sep", "ott": "Oct", "dic": "Dec",
        # 荷兰语
        "januari": "January", "februari": "February", "maart": "March",
        "april": "April", "mei": "May", "juni": "June",
        "juli": "July", "augustus": "August", "september": "September",
        "oktober": "October", "november": "November", "december": "December",
        # 瑞典语
        "januari": "January", "februari": "February", "mars": "March",
        "april": "April", "maj": "May", "juni": "June",
        "juli": "July", "augusti": "August", "september": "September",
        "oktober": "October", "november": "November", "december": "December",
        # 德语
        "januar": "January", "februar": "February", "märz": "March",
        "april": "April", "mai": "May", "juni": "June",
        "juli": "July", "august": "August", "september": "September",
        "oktober": "October", "november": "November", "dezember": "December",
        # 西班牙语
        "enero": "January", "febrero": "February", "marzo": "March",
        "abril": "April", "mayo": "May", "junio": "June",
        "julio": "July", "agosto": "August", "septiembre": "September",
        "octubre": "October", "noviembre": "November", "diciembre": "December",
    }

    # 替换非英语月份
    lower = date_str.lower()
    for local, eng in MONTH_MAP.items():
        if local in lower:
            date_str = date_str.replace(local, eng)
            # 也处理首字母大写
            date_str = date_str.replace(local.capitalize(), eng)
            break

    # 常见格式
    formats = [
        "%d %b %Y %H:%M:%S UTC",       # "1 May 2026 00:09:17 UTC"
        "%d %B %Y %H:%M:%S UTC",        # "2 May 2026 03:04:42 UTC"
        "%d %b %Y %I:%M:%S %p UTC",     # "12 May 2026 4:26:48 AM UTC"
        "%d %B %Y %I:%M:%S %p UTC",     # "12 May 2026 4:26:48 AM UTC"
        "%d.%m.%Y %H:%M:%S UTC",        # "01.05.2026 10:05:35 UTC"
        "%Y-%m-%dT%H:%M:%S%z",          # ISO 8601
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except:
            continue

    # 尝试 pandas 自动解析
    try:
        return pd.to_datetime(date_str).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None


# ============================================================
# 3. 导入广告数据
# ============================================================
def import_advertising():
    print("\n=== 导入广告数据 ===")
    conn = get_db()
    cursor = conn.cursor()
    store_id = get_store_id(cursor)

    ad_files = {
        "UK": "英国站点广告费.xlsx",
        "DE": "德国站点广告费.csv",
        "FR": "法国站点广告费.csv",
        "ES": "西班牙站点广告费.csv",
        "NL": "荷兰站点广告费.csv",
        "BE": "比利时站点广告费.csv",
        "IE": "爱尔兰站点广告费.csv",
    }

    total_imported = 0

    for country_code, filename in ad_files.items():
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [{country_code}] 文件不存在: {filename}")
            continue

        country_id = get_country_id(cursor, country_code)
        if not country_id:
            print(f"  [{country_code}] 国家未找到")
            continue

        # 读取文件
        if filename.endswith(".xlsx"):
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath, encoding="utf-8-sig")

        # UK xlsx 的商品列被拆成了4列，需要合并
        if country_code == "UK":
            # 合并前4列: ASIN + SKU部分
            cols = df.columns.tolist()
            df["商品"] = df[cols[0]].astype(str)
            for i in range(1, 4):
                if i < len(cols):
                    part = df[cols[i]].astype(str).replace("nan", "")
                    df["商品"] = df["商品"] + "-" + part
            # 清理多余的 -
            df["商品"] = df["商品"].str.replace("-$", "", regex=True).str.replace("--", "-")

        imported = 0
        for _, row in df.iterrows():
            product_field = str(row.get("商品", "")).strip()
            if not product_field or product_field == "nan":
                continue

            # 提取 ASIN（取第一段）
            asin = product_field.split("-")[0] if "-" in product_field else product_field

            # 确定货币列名
            if country_code == "UK":
                sales_col = "销售额(GBP)"
                spend_col = "花费(GBP)"
                cpc_col = "CPC(GBP)"
            else:
                sales_col = "销售额(EUR)"
                spend_col = "花费(EUR)"
                cpc_col = "CPC(EUR)"

            sales_val = safe_float(row.get(sales_col, 0))
            roas_val = safe_float(row.get("ROAS", 0))
            conv_rate = safe_float(row.get("转化率", 0))
            impressions = safe_int(row.get("展示次数", 0))
            clicks = safe_int(row.get("点击量", 0))
            ctr_val = safe_float(row.get("CTR", 0))
            spend_val = safe_float(row.get(spend_col, 0))
            cpc_val = safe_float(row.get(cpc_col, 0))
            orders = safe_int(row.get("订单数量", 0))
            acos_val = safe_float(row.get("ACOS", 0))
            ntb_orders = safe_int(row.get("NTB 订单数量", 0))
            ntb_order_pct = safe_float(row.get("NTB 订单数量百分比", 0))
            ntb_sales = safe_float(row.get("NTB 销售额(EUR)", row.get("NTB 销售额(GBP)", 0)))
            new_brand_pct = safe_float(row.get("品牌新客销售额比例", 0))
            visible_impr = safe_int(row.get("可见展示量", 0))

            cursor.execute("""
                INSERT INTO raw_advertising (
                    country_id, store_id, product_field, asin,
                    sales_usd, roas, conversion_rate, impressions, clicks, ctr,
                    spend_usd, cpc, orders, acos,
                    ntb_orders, ntb_order_pct, ntb_sales_usd,
                    new_to_brand_sales_pct, visible_impressions
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
            """, (
                country_id, store_id, product_field, asin,
                sales_val, roas_val, conv_rate, impressions, clicks, ctr_val,
                spend_val, cpc_val, orders, acos_val,
                ntb_orders, ntb_order_pct, ntb_sales,
                new_brand_pct, visible_impr
            ))
            imported += 1

        conn.commit()
        total_imported += imported
        print(f"  [{country_code}] {imported} 条")

    cursor.close()
    conn.close()
    print(f"  广告数据总计: {total_imported} 条")


def safe_float(val):
    try:
        if pd.isna(val):
            return 0.0
        return float(val)
    except:
        return 0.0


def safe_int(val):
    try:
        if pd.isna(val):
            return 0
        return int(float(val))
    except:
        return 0


# ============================================================
# 4. 导入仓储费
# ============================================================
def import_storage_fees():
    print("\n=== 导入仓储费 ===")
    filepath = os.path.join(DATA_DIR, "仓储费.xlsx")
    if not os.path.exists(filepath):
        print("  文件不存在")
        return

    df = pd.read_excel(filepath)
    conn = get_db()
    cursor = conn.cursor()
    store_id = get_store_id(cursor)

    imported = 0
    for _, row in df.iterrows():
        asin = str(row.get("asin", "")).strip()
        if not asin or asin == "nan":
            continue

        country_code = str(row.get("country_code", "")).strip()
        country_id = get_country_id(cursor, country_code)
        if not country_id:
            continue

        cursor.execute("""
            INSERT INTO raw_storage_fee (
                country_id, store_id, asin, fnsku, product_name,
                fulfillment_center, country_code,
                longest_side, median_side, shortest_side, measurement_units,
                weight, weight_units, item_volume, volume_units,
                product_size_tier, average_quantity_on_hand,
                average_quantity_pending_removal, estimated_total_item_volume,
                month_of_charge, storage_utilization_ratio,
                storage_utilization_ratio_units, base_rate,
                utilization_surcharge_rate, avg_qty_for_sus,
                est_vol_for_sus, est_base_msf, est_sus,
                currency, estimated_monthly_storage_fee,
                eligible_for_inventory_discount, qualifies_for_inventory_discount,
                total_incentive_fee_amount, average_quantity_customer_orders
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
        """, (
            country_id, store_id,
            asin,
            str(row.get("fnsku", "")),
            str(row.get("product_name", "")),
            str(row.get("fulfillment_center", "")),
            country_code,
            safe_float(row.get("longest_side")),
            safe_float(row.get("median_side")),
            safe_float(row.get("shortest_side")),
            str(row.get("measurement_units", "")),
            safe_float(row.get("weight")),
            str(row.get("weight_units", "")),
            safe_float(row.get("item_volume")),
            str(row.get("volume_units", "")),
            str(row.get("product_size_tier", "")),
            safe_float(row.get("average_quantity_on_hand")),
            safe_float(row.get("average_quantity_pending_removal")),
            safe_float(row.get("estimated_total_item_volume")),
            str(row.get("month_of_charge", "")),
            safe_float(row.get("storage_utilization_ratio")),
            str(row.get("storage_utilization_ratio_units", "")),
            safe_float(row.get("base_rate")),
            safe_float(row.get("utilization_surcharge_rate")),
            safe_float(row.get("avg_qty_for_sus")),
            safe_float(row.get("est_vol_for_sus")),
            safe_float(row.get("est_base_msf")),
            safe_float(row.get("est_sus")),
            str(row.get("currency", "")),
            safe_float(row.get("estimated_monthly_storage_fee")),
            str(row.get("eligible_for_inventory_discount", "")),
            str(row.get("qualifies_for_inventory_discount", "")),
            safe_float(row.get("total_incentive_fee_amount")),
            safe_float(row.get("average_quantity_customer_orders")),
        ))
        imported += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  仓储费: {imported} 条")


# ============================================================
# 5. 导入超龄仓储费
# ============================================================
def import_aged_storage():
    print("\n=== 导入超龄仓储费 ===")
    filepath = os.path.join(DATA_DIR, "超龄仓储费.csv")
    if not os.path.exists(filepath):
        print("  文件不存在")
        return

    df = pd.read_csv(filepath, encoding="utf-8-sig")
    conn = get_db()
    cursor = conn.cursor()
    store_id = get_store_id(cursor)

    imported = 0
    for _, row in df.iterrows():
        asin = str(row.get("asin", "")).strip()
        if not asin or asin == "nan":
            continue

        country_code = str(row.get("country", "")).strip()
        # 映射：GB → UK
        if country_code == "GB":
            country_code = "UK"
        country_id = get_country_id(cursor, country_code)
        if not country_id:
            continue

        cursor.execute("""
            INSERT INTO raw_long_term_storage (
                country_id, store_id, snapshot_date, sku, fnsku, asin,
                product_name, condition_val, per_unit_volume,
                currency, volume_unit, country,
                qty_charged, amount_charged, surcharge_age_tier, rate_surcharge
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            country_id, store_id,
            str(row.get("snapshot-date", "")),
            str(row.get("sku", "")),
            str(row.get("fnsku", "")),
            asin,
            str(row.get("product-name", "")),
            str(row.get("condition", "")),
            safe_float(row.get("per-unit-volume")),
            str(row.get("currency", "")),
            str(row.get("volume-unit", "")),
            country_code,
            safe_int(row.get("qty-charged")),
            safe_float(row.get("amount-charged")),
            str(row.get("surcharge-age-tier", "")),
            safe_float(row.get("rate-surcharge")),
        ))
        imported += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  超龄仓储费: {imported} 条")


# ============================================================
# 6. 导入退回处理费
# ============================================================
def import_returns():
    print("\n=== 导入退回处理费 ===")
    filepath = os.path.join(DATA_DIR, "退回处理费.csv")
    if not os.path.exists(filepath):
        print("  文件不存在")
        return

    df = pd.read_csv(filepath, encoding="utf-8-sig")
    conn = get_db()
    cursor = conn.cursor()
    store_id = get_store_id(cursor)

    # 退回处理费没有国家列，根据店铺推断（MGK-EU 的退回处理费来自欧洲仓库）
    # 默认归到 DE（德国是欧洲主要仓库所在地）
    default_country_id = get_country_id(cursor, "DE")

    imported = 0
    for _, row in df.iterrows():
        asin = str(row.get("asin", "")).strip()
        if not asin or asin == "nan":
            continue

        cursor.execute("""
            INSERT INTO raw_returns (
                country_id, store_id, asin, asin_fee_category, fnsku,
                product_name, longest_side, median_side, shortest_side,
                measurement_units, unit_weight, dimensional_weight,
                shipping_weight, weight_units, sku_sizetier,
                month_of_shipment, asin_shipped_units,
                asin_return_threshold_percent, asin_return_threshold_units,
                asin_returned_units, sku_returned_units_nsp_exempted,
                sku_returned_units_charged, sku_fee_per_unit,
                sku_returns_fee, month_of_charge, currency
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """, (
            default_country_id, store_id,
            asin,
            str(row.get("asin_fee_category", "")),
            str(row.get("fnsku", "")),
            str(row.get("product_name", "")),
            safe_float(row.get("longest_side")),
            safe_float(row.get("median_side")),
            safe_float(row.get("shortest_side")),
            str(row.get("measurement-units", "")),
            safe_float(row.get("unit_weight")),
            safe_float(row.get("dimensional_weight")),
            safe_float(row.get("shipping_weight")),
            str(row.get("weight_units", "")),
            str(row.get("sku_sizetier", "")),
            str(row.get("month_of_shipment", "")),
            safe_int(row.get("asin_shipped_units")),
            safe_float(row.get("asin_return_threshold_percent")),
            safe_int(row.get("asin_return_threshold_units")),
            safe_int(row.get("asin_returned_units")),
            safe_int(row.get("sku_returned_units_NSP_exempted")),
            safe_int(row.get("sku_returned_units_charged")),
            safe_float(row.get("sku_fee_per_unit")),
            safe_float(row.get("sku_returns_fee")),
            str(row.get("month_of_charge", "")),
            str(row.get("currency", "")),
        ))
        imported += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"  退回处理费: {imported} 条")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("MGK-EU 店铺数据导入")
    print("=" * 60)

    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target == "rates":
            import_exchange_rates()
        elif target == "products":
            import_products()
        elif target == "sales":
            import_sales()
        elif target == "advertising":
            import_advertising()
        elif target == "storage":
            import_storage_fees()
        elif target == "aged":
            import_aged_storage()
        elif target == "returns":
            import_returns()
        else:
            print(f"未知目标: {target}")
            print("用法: python import_mgk_eu.py [rates|products|sales|advertising|storage|aged|returns]")
    else:
        # 全部导入（汇率 → 产品 → 销售 → 广告 → 仓储 → 超龄 → 退回）
        import_exchange_rates()
        import_products()
        import_sales()
        import_advertising()
        import_storage_fees()
        import_aged_storage()
        import_returns()
        print("\n✅ 全部导入完成")
