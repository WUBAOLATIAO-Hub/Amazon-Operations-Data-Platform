"""彻底重建 monthly_summary — 只重建交易数据（按月准确），费用字段清零等待重新导入"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from database import SessionLocal
from models import (
    DimCountry, DimProduct, DimProductCost, DimFreight, DimTime, DimStore,
    DimExchangeRate, MonthlySummary, RawTransaction,
)
from sqlalchemy import text
from decimal import Decimal
from collections import defaultdict


def rebuild():
    db = SessionLocal()
    try:
        # ===== 1. 清空 monthly_summary =====
        db.execute(text("DELETE FROM monthly_summary"))
        db.flush()
        print("✓ 已清空 monthly_summary")

        # ===== 2. 找出所有 (store_id, country_id, time_id) 组合 =====
        rt_combos = db.execute(text("""
            SELECT DISTINCT store_id, country_id, time_id
            FROM raw_transactions
            WHERE store_id IS NOT NULL AND country_id IS NOT NULL AND time_id IS NOT NULL
        """)).fetchall()
        combos = [(r[0], r[1], r[2]) for r in rt_combos]
        print(f"✓ 找到 {len(combos)} 个 (store,country,time) 组合")

        # ===== 3. 预加载维度 =====
        products = {p.id: p for p in db.query(DimProduct).all()}
        times = {t.id: t for t in db.query(DimTime).all()}
        stores = {s.id: s for s in db.query(DimStore).all()}
        countries = {c.id: c for c in db.query(DimCountry).all()}

        # 成本预加载
        cost_by_key = {}
        for pc in db.query(DimProductCost).all():
            cost_by_key[(pc.product_id, pc.year_month)] = (Decimal(str(pc.cost_rmb or 0)), Decimal(str(pc.freight_per_unit or 0)))
        cost_first = {}
        for (pid, ym), (c, f) in cost_by_key.items():
            if pid not in cost_first:
                cost_first[pid] = (c, f)

        freight_map = {}
        for df in db.query(DimFreight).all():
            freight_map[(df.product_id, df.store_id, df.country_id)] = Decimal(str(df.freight_rmb or 0))

        rate_map = {}
        for er in db.query(DimExchangeRate).all():
            rate_map[(er.store_id, er.country_id, er.year_month)] = Decimal(str(er.rate or 0))

        DEFAULT_RATES = {'US':'6.8','UK':'9.0','DE':'7.5','FR':'7.5','ES':'7.5','IT':'7.5',
                         'NL':'7.5','SE':'0.65','BE':'7.5','IE':'7.5','CA':'5.0','MX':'0.4',
                         'AE':'1.85','SA':'1.81','AU':'4.8'}

        def get_rate(store_id, country_id, ym):
            code = countries.get(country_id)
            default = Decimal(DEFAULT_RATES.get(code.code if code else '', '6.8'))
            r = rate_map.get((store_id, country_id, ym))
            if r and r != 0:
                return r
            r = rate_map.get((store_id, country_id, None))
            if r and r != 0:
                return r
            return default

        # 导入 real sku 提取器
        from routers.import_data import _extract_real_sku

        # ===== 4. 按 (store_id, country_id, time_id) 重建 =====
        total_rows = 0
        for (sid, cid, tid) in combos:
            if sid not in stores or cid not in countries or tid not in times:
                continue
            time_obj = times[tid]
            country_obj = countries[cid]
            ym = time_obj.year_month

            # --- 4a. 从 raw_transactions 聚合 ---
            raw_agg = defaultdict(lambda: {
                "ps": Decimal("0"), "pst": Decimal("0"), "pc": Decimal("0"),
                "sct": Decimal("0"), "gwc": Decimal("0"), "gwct": Decimal("0"),
                "promo": Decimal("0"), "promo_tax": Decimal("0"), "mkt": Decimal("0"),
                "sf": Decimal("0"), "fba": Decimal("0"), "adj": Decimal("0"),
                "order_qty": 0, "order_count": 0,
            })
            rt_rows = db.execute(text("""
                SELECT sku, transaction_type,
                       SUM(COALESCE(product_sales,0)) as ps,
                       SUM(COALESCE(product_sales_tax,0)) as pst,
                       SUM(COALESCE(postage_credits,0)) as pc,
                       SUM(COALESCE(shipping_credits_tax,0)) as sct,
                       SUM(COALESCE(gift_wrap_credits,0)) as gwc,
                       SUM(COALESCE(giftwrap_credits_tax,0)) as gwct,
                       SUM(COALESCE(promotional_rebates,0)) as promo,
                       SUM(COALESCE(promotional_rebates_tax,0)) as promo_tax,
                       SUM(COALESCE(marketplace_withheld_tax,0)) as mkt,
                       SUM(COALESCE(selling_fee,0)) as sf,
                       SUM(COALESCE(fba_fee,0)) as fba,
                       SUM(COALESCE(total,0)) as total,
                       SUM(ABS(COALESCE(quantity,0))) as qty,
                       COUNT(*) as cnt
                FROM raw_transactions
                WHERE store_id=:sid AND country_id=:cid AND time_id=:tid
                  AND sku IS NOT NULL AND sku != ''
                GROUP BY sku, transaction_type
            """), {"sid": sid, "cid": cid, "tid": tid}).fetchall()

            for row in rt_rows:
                real_sku = _extract_real_sku(row[0]) or row[0]
                agg = raw_agg[real_sku]
                tt = row[1]
                if tt in ('Order', 'Refund'):
                    agg["ps"] += Decimal(str(row[2] or 0))
                    agg["pst"] += Decimal(str(row[3] or 0))
                    agg["pc"] += Decimal(str(row[4] or 0))
                    agg["sct"] += Decimal(str(row[5] or 0))
                    agg["gwc"] += Decimal(str(row[6] or 0))
                    agg["gwct"] += Decimal(str(row[7] or 0))
                    agg["promo"] += Decimal(str(row[8] or 0))
                    agg["promo_tax"] += Decimal(str(row[9] or 0))
                    agg["mkt"] += Decimal(str(row[10] or 0))
                    agg["sf"] += Decimal(str(row[11] or 0))
                    agg["fba"] += Decimal(str(row[12] or 0))
                if tt == 'Order':
                    agg["order_qty"] += int(row[14] or 0)
                    agg["order_count"] += int(row[15] or 0)
                elif tt == 'Adjustment':
                    agg["adj"] += Decimal(str(row[13] or 0))

            # --- 4b. 为每个 SKU 创建 monthly_summary ---
            matched_products = {}
            for p in products.values():
                if p.store_id == sid and p.sku:
                    if p.sku not in matched_products:
                        matched_products[p.sku] = p

            for sku, agg in raw_agg.items():
                product = matched_products.get(sku)
                if not product:
                    continue

                er = get_rate(sid, cid, ym)
                oq = agg["order_qty"]
                oc = agg["order_count"]

                # 产品成本
                cost_per_unit, freight_per_unit = Decimal("0"), Decimal("0")
                pc = cost_by_key.get((product.id, ym))
                if pc:
                    cost_per_unit, freight_per_unit = pc
                elif product.id in cost_first:
                    cost_per_unit, freight_per_unit = cost_first[product.id]
                ff = freight_map.get((product.id, sid, cid))
                if ff is not None:
                    freight_per_unit = ff

                cost_rmb = (cost_per_unit * oq).quantize(Decimal("0.01"))
                freight_rmb = (freight_per_unit * oq).quantize(Decimal("0.01"))

                # 费用字段全部归零，等重新导入
                net_amazon = (
                    agg["ps"] + agg["pst"] + agg["pc"] + agg["sct"] + agg["gwc"]
                    + agg["gwct"] + agg["promo"] + agg["promo_tax"] + agg["mkt"]
                    + agg["sf"] + agg["fba"] + agg["adj"]
                )
                net_profit = (
                    net_amazon * er - cost_rmb - freight_rmb
                ).quantize(Decimal("0.01"))

                sales_rmb = (agg["ps"] * er).quantize(Decimal("0.01"))
                profit_rate = (net_profit / sales_rmb).quantize(Decimal("0.0001")) if sales_rmb != 0 else Decimal("0")
                amazon_payout = (agg["ps"] + agg["sf"] + agg["fba"]).quantize(Decimal("0.01"))

                ms = MonthlySummary(
                    country_id=cid, store_id=sid, product_id=product.id, time_id=tid,
                    order_count=oc, order_qty=oq,
                    product_sales_usd=agg["ps"],
                    product_sales_tax=agg["pst"],
                    postage_credits=agg["pc"],
                    shipping_credits_tax=agg["sct"],
                    gift_wrap_credits=agg["gwc"],
                    giftwrap_credits_tax=agg["gwct"],
                    promo_rebate_usd=agg["promo"],
                    promo_rebate_tax_usd=agg["promo_tax"],
                    marketplace_withheld_tax_usd=agg["mkt"],
                    commission_usd=agg["sf"],
                    fba_fee_usd=agg["fba"],
                    adjustment_usd=agg["adj"],
                    product_sales_rmb=sales_rmb,
                    amazon_payout_usd=amazon_payout,
                    product_cost_rmb=cost_rmb,
                    freight_cost_rmb=freight_rmb,
                    # 费用全部归零，等待重新导入
                    ad_spend_usd=Decimal("0"),
                    storage_fee_usd=Decimal("0"),
                    returns_fee_usd=Decimal("0"),
                    inbound_fee_usd=Decimal("0"),
                    removal_fee_usd=Decimal("0"),
                    exchange_rate=er,
                    net_profit_rmb=net_profit,
                    net_profit_rate=profit_rate,
                )
                db.add(ms)
                total_rows += 1

        db.commit()
        print(f"✓ 重建完成，共 {total_rows} 行 monthly_summary")

        # ===== 5. 验证 =====
        sid = db.query(DimStore).filter(DimStore.code == 'MGT-EU').first()
        cid = db.query(DimCountry).filter(DimCountry.code == 'UK').first()
        tid = db.query(DimTime).filter(DimTime.year_month == '2026-04').first()
        if sid and cid and tid:
            ms_rows = db.query(MonthlySummary).filter(
                MonthlySummary.store_id == sid.id,
                MonthlySummary.country_id == cid.id,
                MonthlySummary.time_id == tid.id,
            ).all()
            total_ps = sum(float(r.product_sales_usd or 0) for r in ms_rows)
            total_np = sum(float(r.net_profit_rmb or 0) for r in ms_rows)
            print(f"\n[MGT-EU UK 04 验证]")
            print(f"  行数: {len(ms_rows)}")
            print(f"  product_sales_usd: {total_ps:.2f} (期望 42904.34)")
            print(f"  net_profit_rmb (未含费用): {total_np:.2f}")

            rt_ps = db.execute(text("""
                SELECT SUM(COALESCE(product_sales,0))
                FROM raw_transactions
                WHERE store_id=:sid AND country_id=:cid AND time_id=:tid
                  AND transaction_type IN ('Order','Refund')
            """), {"sid": sid.id, "cid": cid.id, "tid": tid.id}).fetchone()
            print(f"  raw_transactions PS: {float(rt_ps[0] or 0):.2f}")
            print(f"  PS gap: {total_ps - float(rt_ps[0] or 0):.2f}")

    finally:
        db.close()


if __name__ == '__main__':
    rebuild()
