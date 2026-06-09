-- Migration V8: 店铺隔离修复
-- 解决：dim_product / dim_freight / raw_returns 跨店铺数据覆盖问题

USE lmg_platform;

-- ============================================================
-- 1. dim_product 加 store_id，改为 (asin, store_id) 联合唯一
-- ============================================================

-- 先去掉旧的唯一键
ALTER TABLE dim_product DROP INDEX IF EXISTS uk_asin;

-- 加 store_id 字段
ALTER TABLE dim_product
  ADD COLUMN store_id INT DEFAULT NULL AFTER id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- 建新的联合唯一键
ALTER TABLE dim_product
  ADD UNIQUE KEY uk_asin_store (asin, store_id);

-- ============================================================
-- 2. dim_freight 加 store_id，改为 (product_id, country_id, store_id) 联合唯一
-- ============================================================

-- 先去掉旧的唯一键
ALTER TABLE dim_freight DROP INDEX IF EXISTS uk_product_country;

-- 加 store_id 字段
ALTER TABLE dim_freight
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- 建新的联合唯一键
ALTER TABLE dim_freight
  ADD UNIQUE KEY uk_product_country_store (product_id, country_id, store_id);
