#!/usr/bin/env python3
"""
MGK-EU 利润计算脚本

利润公式（每笔交易）：
  净销售额(外币) = product_sales（已含退款，Order+Refund合并）
  佣金(外币)     = ABS(selling_fees)
  FBA费(外币)    = ABS(fba_fees)
  其他交易费(外币) = ABS(other_transaction_fees)

  亚马逊到账(外币) = product_sales + selling_fees + fba_fees + other_transaction_fees + other_amount

  产品成本(RMB) = cost_rmb × quantity
  运费(RMB)     = freight_rmb × quantity（从 dim_freight 按国家取）

  广告费(RMB)   = 广告花费(外币) × 汇率（按 ASIN 分摊）

  净利润(RMB) = 亚马逊到账(外币) × 汇率
               - 产品成本(RMB)
               - 运费(RMB)
               - 广告费(RMB)
               - 仓储费(RMB)
               - 退回处理费(RMB)

  净利率 = 净利润 / (净销售额 × 汇率)
"""
import os
import sys
import mysql.connector
from decimal import Decimal
from collections import defaultdict

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "lmg_platform",
    "charset": "utf8mb4",
}

STORE_CODE = "MGK-EU"
EXCHANGE_MONTH = "2026-05"  # 默认汇率月份


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def calculate_by_product_country_month():
    """
    按 产品 × 国家 × 月份 汇总计算利润
    """
    print("\n=== MGK-EU 利润计算（产品 × 国家 × 月份）===\n")
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # 1. 获取 SKU → ASIN 映射 + 成本（按店铺过滤）
    cursor.execute("""
        SELECT dp.id, dp.asin, dp.sku, dp.cost_rmb
        FROM dim_product dp
        JOIN dim_store ds ON dp.store_id = ds.id
        WHERE ds.store_code = %s
    """, (STORE_CODE,))
    products = {}
    sku_to_product = {}
    for row in cursor.fetchall():
        products[row["id"]] = row
        if row["sku"]:
            sku_to_product[row["sku"]] = row

    # 2. 获取运费映射: product_id → {country_id: freight_rmb}（按店铺过滤）
    cursor.execute("""
        SELECT df.product_id, df.country_id, df.freight_rmb, dc.code as country_code
        FROM dim_freight df
        JOIN dim_country dc ON df.country_id = dc.id
        JOIN dim_store ds ON df.store_id = ds.id
        WHERE ds.store_code = %s
    """, (STORE_CODE,))
    freight_map = defaultdict(dict)
    for row in cursor.fetchall():
        freight_map[row["product_id"]][row["country_code"]] = Decimal(str(row["freight_rmb"]))

    # 3. 获取国家 + 汇率映射
    cursor.execute("""
        SELECT dc.id, dc.code, COALESCE(der.rate, 0) as rate
        FROM dim_country dc
        LEFT JOIN dim_exchange_rate der ON der.country_id = dc.id AND der.`year_month` = %s
    """, (EXCHANGE_MONTH,))
    country_map = {}
    for row in cursor.fetchall():
        country_map[row["id"]] = {"code": row["code"], "rate": Decimal(str(row["rate"]))}

    # 4. 获取广告费：按 ASIN × 国家汇总
    cursor.execute("""
        SELECT ra.asin, dc.code as country_code, SUM(ra.spend_usd) as total_spend
        FROM raw_advertising ra
        JOIN dim_country dc ON ra.country_id = dc.id
        JOIN dim_store ds ON ra.store_id = ds.id
        WHERE ds.store_code = %s
        GROUP BY ra.asin, dc.code
    """, (STORE_CODE,))
    ad_spend = {}
    for row in cursor.fetchall():
        ad_spend[(row["asin"], row["country_code"])] = Decimal(str(row["total_spend"]))

    # 5. 获取仓储费：按 ASIN × 国家汇总
    cursor.execute("""
        SELECT rsf.asin, dc.code as country_code,
               SUM(rsf.estimated_monthly_storage_fee) as total_storage
        FROM raw_storage_fee rsf
        JOIN dim_country dc ON rsf.country_id = dc.id
        JOIN dim_store ds ON rsf.store_id = ds.id
        WHERE ds.store_code = %s
        GROUP BY rsf.asin, dc.code
    """, (STORE_CODE,))
    storage_fees = {}
    for row in cursor.fetchall():
        storage_fees[(row["asin"], row["country_code"])] = Decimal(str(row["total_storage"]))

    # 6. 获取超龄仓储费：按 ASIN × 国家汇总
    cursor.execute("""
        SELECT rlt.asin, dc.code as country_code,
               SUM(rlt.amount_charged) as total_aged
        FROM raw_long_term_storage rlt
        JOIN dim_country dc ON rlt.country_id = dc.id
        JOIN dim_store ds ON rlt.store_id = ds.id
        WHERE ds.store_code = %s
        GROUP BY rlt.asin, dc.code
    """, (STORE_CODE,))
    aged_fees = {}
    for row in cursor.fetchall():
        aged_fees[(row["asin"], row["country_code"])] = Decimal(str(row["total_aged"]))

    # 7. 获取退回处理费：按 ASIN 汇总
    cursor.execute("""
        SELECT rr.asin, SUM(rr.sku_returns_fee) as total_returns
        FROM raw_returns rr
        JOIN dim_store ds ON rr.store_id = ds.id
        WHERE ds.store_code = %s
        GROUP BY rr.asin
    """, (STORE_CODE,))
    returns_fees = {}
    for row in cursor.fetchall():
        returns_fees[row["asin"]] = Decimal(str(row["total_returns"]))

    # 8. 获取交易明细：按 SKU × 国家 × 月份 汇总
    cursor.execute("""
        SELECT
            rt.sku,
            dc.code as country_code,
            dt.`year_month`,
            SUM(rt.product_sales) as sum_product_sales,
            SUM(rt.selling_fee) as sum_selling_fee,
            SUM(rt.fba_fee) as sum_fba_fee,
            SUM(rt.other_transaction_fee) as sum_other_txn_fee,
            SUM(rt.other_amount) as sum_other,
            SUM(rt.total) as sum_total,
            SUM(rt.quantity) as sum_quantity,
            COUNT(*) as txn_count
        FROM raw_transactions rt
        JOIN dim_country dc ON rt.country_id = dc.id
        JOIN dim_store ds ON rt.store_id = ds.id
        JOIN dim_time dt ON dt.time_year = YEAR(rt.transaction_date)
                        AND dt.time_month = MONTH(rt.transaction_date)
        WHERE ds.store_code = %s
          AND rt.transaction_type IN ('Order', 'Refund')
        GROUP BY rt.sku, dc.code, dt.`year_month`
    """, (STORE_CODE,))

    results = cursor.fetchall()

    # 9. 计算利润
    print(f"{'SKU':<20} {'国家':<5} {'月份':<8} {'销量':>5} {'到账(外币)':>12} {'到账(RMB)':>12} "
          f"{'成本(RMB)':>10} {'运费(RMB)':>10} {'广告(RMB)':>10} {'仓储(RMB)':>10} "
          f"{'净利润(RMB)':>12} {'净利率':>8}")
    print("-" * 150)

    total_profit = Decimal("0")
    total_sales_rmb = Decimal("0")
    summary_by_country = defaultdict(lambda: {"profit": Decimal("0"), "sales_rmb": Decimal("0")})
    summary_by_product = defaultdict(lambda: {"profit": Decimal("0"), "sales_rmb": Decimal("0")})

    for row in results:
        sku = row["sku"]
        country_code = row["country_code"]
        year_month = row["year_month"]
        quantity = int(row["sum_quantity"] or 0)

        if quantity <= 0:
            continue

        # 汇率（从数据库读取）
        rate = Decimal("1")
        for cid, cinfo in country_map.items():
            if cinfo["code"] == country_code:
                rate = cinfo["rate"]
                break

        # 交易金额（外币）
        product_sales = Decimal(str(row["sum_product_sales"] or 0))
        selling_fee = Decimal(str(row["sum_selling_fee"] or 0))
        fba_fee = Decimal(str(row["sum_fba_fee"] or 0))
        other_txn_fee = Decimal(str(row["sum_other_txn_fee"] or 0))
        other_amount = Decimal(str(row["sum_other"] or 0))
        total = Decimal(str(row["sum_total"] or 0))

        # 亚马逊到账（外币）= total 已经是扣完所有费用后的金额
        amazon_payout = total

        # 到账转 RMB
        payout_rmb = amazon_payout * rate

        # 产品成本（RMB）
        product_info = sku_to_product.get(sku)
        cost_rmb = Decimal("0")
        product_id = None
        asin = None
        if product_info:
            cost_rmb = Decimal(str(product_info["cost_rmb"])) * quantity
            product_id = product_info["id"]
            asin = product_info["asin"]

        # 运费（RMB）
        freight_rmb = Decimal("0")
        if product_id and country_code in freight_map.get(product_id, {}):
            freight_rmb = freight_map[product_id][country_code] * quantity

        # 广告费（RMB）— 按 ASIN × 国家分摊
        ad_spend_rmb = Decimal("0")
        if asin:
            ad_local = ad_spend.get((asin, country_code), Decimal("0"))
            ad_spend_rmb = ad_local * rate

        # 仓储费（RMB）
        storage_rmb = Decimal("0")
        if asin:
            storage_local = storage_fees.get((asin, country_code), Decimal("0"))
            aged_local = aged_fees.get((asin, country_code), Decimal("0"))
            storage_rmb = (storage_local + aged_local) * rate

        # 退回处理费（RMB）
        returns_rmb = Decimal("0")
        if asin:
            returns_local = returns_fees.get(asin, Decimal("0"))
            returns_rmb = returns_local * rate

        # 净利润
        net_profit = payout_rmb - cost_rmb - freight_rmb - ad_spend_rmb - storage_rmb - returns_rmb

        # 净利率
        sales_rmb = product_sales * rate
        net_margin = (net_profit / sales_rmb * 100) if sales_rmb != 0 else Decimal("0")

        total_profit += net_profit
        total_sales_rmb += sales_rmb
        summary_by_country[country_code]["profit"] += net_profit
        summary_by_country[country_code]["sales_rmb"] += sales_rmb
        if asin:
            summary_by_product[asin]["profit"] += net_profit
            summary_by_product[asin]["sales_rmb"] += sales_rmb

        print(f"{sku:<20} {country_code:<5} {year_month:<8} {quantity:>5} "
              f"{amazon_payout:>12.2f} {payout_rmb:>12.2f} "
              f"{cost_rmb:>10.2f} {freight_rmb:>10.2f} {ad_spend_rmb:>10.2f} {storage_rmb:>10.2f} "
              f"{net_profit:>12.2f} {net_margin:>7.1f}%")

    # 汇总
    print("\n" + "=" * 80)
    print("按国家汇总：")
    print(f"{'国家':<6} {'销售额(RMB)':>15} {'净利润(RMB)':>15} {'净利率':>8}")
    print("-" * 50)
    for code in sorted(summary_by_country.keys()):
        d = summary_by_country[code]
        margin = (d["profit"] / d["sales_rmb"] * 100) if d["sales_rmb"] != 0 else 0
        print(f"{code:<6} {d['sales_rmb']:>15,.2f} {d['profit']:>15,.2f} {margin:>7.1f}%")

    total_margin = (total_profit / total_sales_rmb * 100) if total_sales_rmb != 0 else 0
    print("-" * 50)
    print(f"{'合计':<6} {total_sales_rmb:>15,.2f} {total_profit:>15,.2f} {total_margin:>7.1f}%")

    cursor.close()
    conn.close()

    return {
        "total_profit": total_profit,
        "total_sales_rmb": total_sales_rmb,
        "total_margin": total_margin,
        "by_country": dict(summary_by_country),
        "by_product": dict(summary_by_product),
    }


if __name__ == "__main__":
    calculate_by_product_country_month()
