-- Migration V7: MGK-EU 新店铺支持
-- 核心改动：运费从 dim_product 拆出，支持多国家独立运费

USE lmg_platform;

-- ============================================================
-- 1. dim_country 扩展（新增 MGK-EU 涉及的国家）
-- ============================================================
INSERT INTO dim_country (code, name, currency, exchange_rate) VALUES
('FR', '法国', 'EUR', 7.6200),
('ES', '西班牙', 'EUR', 7.6200),
('IT', '意大利', 'EUR', 7.6200),
('NL', '荷兰', 'EUR', 7.6200),
('SE', '瑞典', 'SEK', 0.6500),
('BE', '比利时', 'EUR', 7.6200),
('IE', '爱尔兰', 'EUR', 7.6200),
('AE', '阿联酋', 'AED', 1.8600),
('SA', '沙特', 'SAR', 1.8100);

-- 更新已有国家汇率
UPDATE dim_country SET exchange_rate = 9.2300 WHERE code = 'UK';
UPDATE dim_country SET exchange_rate = 7.6200 WHERE code = 'DE';

-- ============================================================
-- 2. dim_product 改造：去掉 freight_per_unit，加重量
-- ============================================================
ALTER TABLE dim_product
  DROP COLUMN IF EXISTS freight_per_unit,
  DROP COLUMN IF EXISTS exchange_rate,
  ADD COLUMN weight DECIMAL(10,4) DEFAULT 0 COMMENT '重量(kg)' AFTER cost_rmb;

-- ============================================================
-- 3. 新增运费表：dim_freight（产品 × 国家）
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_freight (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    country_id INT NOT NULL,
    freight_rmb DECIMAL(10,2) NOT NULL COMMENT '单件运费(RMB)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES dim_product(id),
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    UNIQUE KEY uk_product_country (product_id, country_id)
);

-- ============================================================
-- 4. dim_time 扩展
-- ============================================================
INSERT INTO dim_time (time_year, time_month, `year_month`) VALUES
(2026, 5, '2026-05')
ON DUPLICATE KEY UPDATE time_year = time_year;

-- ============================================================
-- 5. store 表：区分不同店铺
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_store (
    id INT PRIMARY KEY AUTO_INCREMENT,
    store_code VARCHAR(20) NOT NULL UNIQUE COMMENT '店铺代码: MGK-EU, LMK-US 等',
    store_name VARCHAR(100) NOT NULL COMMENT '店铺名称',
    marketplace VARCHAR(50) COMMENT '平台: Amazon',
    region VARCHAR(50) COMMENT '地区: EU, US, JP 等',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO dim_store (store_code, store_name, marketplace, region) VALUES
('MGK-EU', 'MangoKit 欧洲站', 'Amazon', 'EU');

-- ============================================================
-- 6. raw_transactions 加 store_id
-- ============================================================
ALTER TABLE raw_transactions
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- ============================================================
-- 7. raw_advertising 加 store_id
-- ============================================================
ALTER TABLE raw_advertising
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- ============================================================
-- 8. raw_storage_fee 加 store_id
-- ============================================================
ALTER TABLE raw_storage_fee
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- ============================================================
-- 9. raw_long_term_storage 加 store_id
-- ============================================================
ALTER TABLE raw_long_term_storage
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);

-- ============================================================
-- 10. raw_returns 加 store_id
-- ============================================================
ALTER TABLE raw_returns
  ADD COLUMN store_id INT DEFAULT NULL AFTER country_id,
  ADD FOREIGN KEY (store_id) REFERENCES dim_store(id);
