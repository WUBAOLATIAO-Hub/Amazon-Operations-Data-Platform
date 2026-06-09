-- Migration v5: 添加促销折扣、促销折扣税、亚马逊代扣税字段
-- 执行方式: mysql -u root lmg_platform < migration_v5.sql

-- 1. 添加新字段
ALTER TABLE monthly_summary
    ADD COLUMN promo_rebate_usd DECIMAL(12,2) DEFAULT 0 AFTER inbound_fee_usd,
    ADD COLUMN promo_rebate_tax_usd DECIMAL(12,2) DEFAULT 0 AFTER promo_rebate_usd,
    ADD COLUMN marketplace_withheld_tax_usd DECIMAL(12,2) DEFAULT 0 AFTER promo_rebate_tax_usd;

-- 2. 从 raw_transactions 聚合数据回填（仅 Order/Refund 类型）
UPDATE monthly_summary ms
INNER JOIN (
    SELECT
        rt.country_id,
        rt.store_id,
        rt.product_id,
        dt.time_year AS y,
        dt.time_month AS m,
        SUM(rt.promotional_rebates) AS promo,
        SUM(rt.promotional_rebates_tax) AS promo_tax,
        SUM(rt.marketplace_withheld_tax) AS mkt_tax
    FROM raw_transactions rt
    JOIN dim_time dt ON 1=1
    WHERE rt.transaction_type IN ('Order', 'Refund')
    GROUP BY rt.country_id, rt.store_id, rt.product_id, dt.time_year, dt.time_month
) agg ON ms.country_id = agg.country_id
    AND ms.store_id = agg.store_id
    AND ms.product_id = agg.product_id
    JOIN dim_time dt2 ON ms.time_id = dt2.id AND dt2.time_year = agg.y AND dt2.time_month = agg.m
SET
    ms.promo_rebate_usd = agg.promo,
    ms.promo_rebate_tax_usd = agg.promo_tax,
    ms.marketplace_withheld_tax_usd = agg.mkt_tax;

-- 3. 修正 product_sales_usd：减去 promotional_rebates（之前错误地加进去了）
UPDATE monthly_summary ms
SET ms.product_sales_usd = ms.product_sales_usd - ms.promo_rebate_usd
WHERE ms.promo_rebate_usd != 0;

-- 4. 重新计算 product_sales_rmb
UPDATE monthly_summary ms
SET ms.product_sales_rmb = (ms.product_sales_usd * ms.exchange_rate)
WHERE ms.exchange_rate > 0;

-- 5. 重新计算净利润（需要通过应用层调用 /api/import/recalculate 或手动计算）
-- 净利润变化 = 旧净利润 - promo_rebate_usd * rate - promo_rebate_tax_usd * rate - marketplace_withheld_tax_usd * rate
-- 注意：product_sales_usd 已经减去了 promo，所以 product_sales_rmb 变化 = -promo * rate
-- 净利润变化 = -promo * rate（来自 product_sales_rmb 减少）- promo * rate（新增扣除）= -2 * promo * rate
-- 但实际上 promo 通常是负数（折扣），所以 -2 * 负数 = 正数，净利润反而会增加
-- 最安全的方式是通过应用层 recalculate 接口重新计算
