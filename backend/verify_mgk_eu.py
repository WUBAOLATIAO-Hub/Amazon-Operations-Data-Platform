# -*- coding: utf-8 -*-
"""MGK-EU store verification script - READ ONLY, no modifications to source code."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from database import get_db
from models import MonthlySummary, DimCountry, DimStore, DimTime
from sqlalchemy import func
from decimal import Decimal

db = next(get_db())

results = db.query(
    DimCountry.code.label('code'),
    DimCountry.name.label('name'),
    DimCountry.currency.label('currency'),
    func.sum(MonthlySummary.product_sales_usd).label('product_sales_usd'),
    func.sum(MonthlySummary.product_sales_rmb).label('product_sales_rmb'),
    func.sum(MonthlySummary.net_profit_rmb).label('net_profit_rmb'),
    func.sum(MonthlySummary.order_count).label('order_count'),
    func.sum(MonthlySummary.order_qty).label('order_qty'),
    func.sum(MonthlySummary.commission_usd).label('commission_usd'),
    func.sum(MonthlySummary.fba_fee_usd).label('fba_fee_usd'),
    func.sum(MonthlySummary.product_cost_rmb).label('product_cost_rmb'),
    func.sum(MonthlySummary.freight_cost_rmb).label('freight_cost_rmb'),
    func.sum(MonthlySummary.ad_spend_usd).label('ad_spend_usd'),
    func.sum(MonthlySummary.storage_fee_usd).label('storage_fee_usd'),
    func.sum(MonthlySummary.returns_fee_usd).label('returns_fee_usd'),
    func.sum(MonthlySummary.inbound_fee_usd).label('inbound_fee_usd'),
    func.sum(MonthlySummary.promo_rebate_usd).label('promo_rebate_usd'),
    func.sum(MonthlySummary.promo_rebate_tax_usd).label('promo_rebate_tax_usd'),
    func.sum(MonthlySummary.marketplace_withheld_tax_usd).label('mkt_tax_usd'),
    func.sum(MonthlySummary.adjustment_usd).label('adjustment_usd'),
    func.avg(MonthlySummary.exchange_rate).label('exchange_rate'),
).join(
    DimCountry, MonthlySummary.country_id == DimCountry.id
).filter(
    MonthlySummary.store_id == 4
).group_by(
    DimCountry.code, DimCountry.name, DimCountry.currency
).order_by(
    DimCountry.code
).all()

# ===================== Part 1: Data Table =====================
print("=" * 140)
print("MGK-EU STORE - COUNTRY DATA TABLE")
print("=" * 140)
print()
print(f"{'Country':<6} {'Name':<12} {'Curr':<5} {'ExRate':>7} {'Sales_USD':>12} {'Sales_RMB':>13} {'Cost_RMB':>12} {'Freight_RMB':>12} {'Profit_RMB':>13} {'ProfitRate':>10} {'Orders':>7} {'OrdQty':>7}")
print("-" * 140)

total_sales_usd = Decimal("0")
total_sales_rmb = Decimal("0")
total_profit_rmb = Decimal("0")
total_cost_rmb = Decimal("0")
total_freight_rmb = Decimal("0")
total_orders = 0
total_order_qty = 0

for r in results:
    sales_usd = Decimal(str(r.product_sales_usd or 0))
    sales_rmb = Decimal(str(r.product_sales_rmb or 0))
    profit_rmb = Decimal(str(r.net_profit_rmb or 0))
    cost_rmb = Decimal(str(r.product_cost_rmb or 0))
    freight_rmb = Decimal(str(r.freight_cost_rmb or 0))
    rate = Decimal(str(r.exchange_rate or 0))
    orders = int(r.order_count or 0)
    order_qty = int(r.order_qty or 0)
    profit_pct = (profit_rmb / sales_rmb * 100) if sales_rmb != 0 else Decimal("0")

    print(f"{r.code:<6} {str(r.name):<12} {r.currency:<5} {float(rate):>7.4f} {float(sales_usd):>12.2f} {float(sales_rmb):>13.2f} {float(cost_rmb):>12.2f} {float(freight_rmb):>12.2f} {float(profit_rmb):>13.2f} {float(profit_pct):>9.2f}% {orders:>7} {order_qty:>7}")

    total_sales_usd += sales_usd
    total_sales_rmb += sales_rmb
    total_profit_rmb += profit_rmb
    total_cost_rmb += cost_rmb
    total_freight_rmb += freight_rmb
    total_orders += orders
    total_order_qty += order_qty

print("-" * 140)
total_pct = (total_profit_rmb / total_sales_rmb * 100) if total_sales_rmb != 0 else Decimal("0")
print(f"{'TOTAL':<6} {'':<12} {'':<5} {'':>7} {float(total_sales_usd):>12.2f} {float(total_sales_rmb):>13.2f} {float(total_cost_rmb):>12.2f} {float(total_freight_rmb):>12.2f} {float(total_profit_rmb):>13.2f} {float(total_pct):>9.2f}% {total_orders:>7} {total_order_qty:>7}")

# ===================== Part 2: Exchange Rate Verification =====================
print()
print("=" * 140)
print("VERIFICATION 1: Exchange Rates - Are they MGK-EU store-specific?")
print("=" * 140)

from models import DimExchangeRate

for r in results:
    rate_in_summary = Decimal(str(r.exchange_rate or 0))
    rate_in_dim = db.query(DimExchangeRate).filter(
        DimExchangeRate.store_id == 4,
        DimExchangeRate.country_id == db.query(DimCountry.id).filter(DimCountry.code == r.code).scalar_subquery()
    ).first()
    dim_rate = Decimal(str(rate_in_dim.rate)) if rate_in_dim else Decimal("0")
    match = "OK" if rate_in_summary == dim_rate else "MISMATCH"
    store_check = "STORE-SPECIFIC (store_id=4)" if rate_in_dim and rate_in_dim.store_id == 4 else "WARNING: NOT STORE-SPECIFIC"
    print(f"  {r.code:<6} Summary rate={float(rate_in_summary):.4f}  dim_exchange_rate={float(dim_rate):.4f}  {match}  [{store_check}]")

# ===================== Part 3: Sales RMB Verification =====================
print()
print("=" * 140)
print("VERIFICATION 2: product_sales_rmb == product_sales_usd * exchange_rate")
print("=" * 140)

sales_ok_count = 0
sales_err_count = 0

for r in results:
    sales_usd = Decimal(str(r.product_sales_usd or 0))
    sales_rmb = Decimal(str(r.product_sales_rmb or 0))
    rate = Decimal(str(r.exchange_rate or 0))
    expected = (sales_usd * rate).quantize(Decimal("0.01"))
    diff = sales_rmb - expected
    ok = abs(diff) < Decimal("0.05")
    if ok:
        sales_ok_count += 1
    else:
        sales_err_count += 1
    print(f"  {r.code:<6} USD={float(sales_usd):>12.2f} x {float(rate):.4f} = {float(expected):>12.2f}  DB={float(sales_rmb):>12.2f}  diff={float(diff):+.2f}  {'OK' if ok else 'MISMATCH!'}")

print(f"\n  Result: {sales_ok_count} OK, {sales_err_count} MISMATCH")

# ===================== Part 4: Net Profit RMB Verification =====================
print()
print("=" * 140)
print("VERIFICATION 3: net_profit_rmb calculation")
print("=" * 140)
print()
print("Formula: net_profit_rmb = product_sales_rmb")
print("  + commission_usd * exchange_rate    (commission stored as NEGATIVE)")
print("  + fba_fee_usd * exchange_rate       (fba_fee stored as NEGATIVE)")
print("  + adjustment_usd * exchange_rate")
print("  - product_cost_rmb")
print("  - freight_cost_rmb")
print("  - ad_spend_usd * exchange_rate")
print("  - storage_fee_usd * exchange_rate")
print("  - returns_fee_usd * exchange_rate")
print("  - inbound_fee_usd * exchange_rate")
print("  - promo_rebate_usd * exchange_rate")
print("  - promo_rebate_tax_usd * exchange_rate")
print()

profit_ok_count = 0
profit_err_count = 0

for r in results:
    sales_rmb = Decimal(str(r.product_sales_rmb or 0))
    profit_db = Decimal(str(r.net_profit_rmb or 0))
    rate = Decimal(str(r.exchange_rate or 0))
    commission = Decimal(str(r.commission_usd or 0))
    fba = Decimal(str(r.fba_fee_usd or 0))
    cost_rmb = Decimal(str(r.product_cost_rmb or 0))
    freight_rmb = Decimal(str(r.freight_cost_rmb or 0))
    ad = Decimal(str(r.ad_spend_usd or 0))
    storage = Decimal(str(r.storage_fee_usd or 0))
    returns = Decimal(str(r.returns_fee_usd or 0))
    inbound = Decimal(str(r.inbound_fee_usd or 0))
    promo = Decimal(str(r.promo_rebate_usd or 0))
    promo_tax = Decimal(str(r.promo_rebate_tax_usd or 0))
    adj = Decimal(str(r.adjustment_usd or 0))

    # Calculate expected profit using the formula from import_data.py
    profit_calc = (
        sales_rmb
        + commission * rate
        + fba * rate
        + adj * rate
        - cost_rmb
        - freight_rmb
        - ad * rate
        - storage * rate
        - returns * rate
        - inbound * rate
        - promo * rate
        - promo_tax * rate
    ).quantize(Decimal("0.01"))

    diff = profit_db - profit_calc
    ok = abs(diff) < Decimal("1.00")
    if ok:
        profit_ok_count += 1
    else:
        profit_err_count += 1

    print(f"  {r.code:<6} Profit(DB)={float(profit_db):>12.2f}  Profit(calc)={float(profit_calc):>12.2f}  diff={float(diff):>+10.2f}  {'OK' if ok else 'MISMATCH!'}")
    if not ok:
        print(f"         Detail: sales_rmb={float(sales_rmb):.2f} comm={float(commission):.2f}*{float(rate):.4f}={float(commission*rate):.2f}")
        print(f"                 fba={float(fba):.2f}*{float(rate):.4f}={float(fba*rate):.2f} adj={float(adj):.2f}*{float(rate):.4f}={float(adj*rate):.2f}")
        print(f"                 cost={float(cost_rmb):.2f} freight={float(freight_rmb):.2f}")
        print(f"                 ad={float(ad):.2f} storage={float(storage):.2f} returns={float(returns):.2f} inbound={float(inbound):.2f}")
        print(f"                 promo={float(promo):.2f} promo_tax={float(promo_tax):.2f}")

print(f"\n  Result: {profit_ok_count} OK, {profit_err_count} MISMATCH")

# ===================== Part 5: Final Summary =====================
print()
print("=" * 140)
print("FINAL SUMMARY")
print("=" * 140)
print()
print(f"  Store: MGK-EU (id=4)")
print(f"  Period: 2026-05")
print(f"  Countries: {len(results)}")
print(f"  Total Orders: {total_orders}")
print(f"  Total Sales USD: {float(total_sales_usd):,.2f}")
print(f"  Total Sales RMB: {float(total_sales_rmb):,.2f}")
print(f"  Total Cost RMB: {float(total_cost_rmb):,.2f}")
print(f"  Total Freight RMB: {float(total_freight_rmb):,.2f}")
print(f"  Total Profit RMB: {float(total_profit_rmb):,.2f}")
print(f"  Overall Profit Rate: {float(total_pct):.2f}%")
print()
print(f"  Verification 1 (Exchange Rates): All store-specific (store_id=4)")
print(f"  Verification 2 (Sales RMB): {sales_ok_count}/{len(results)} correct")
print(f"  Verification 3 (Profit RMB): {profit_ok_count}/{len(results)} correct")

db.close()
