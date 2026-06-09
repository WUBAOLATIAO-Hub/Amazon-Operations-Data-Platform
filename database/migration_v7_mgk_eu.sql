-- Migration V7: MGK-EU 新店铺支持
-- 适配实际数据库结构

USE lmg_platform;

-- ============================================================
-- 1. dim_country 新增 MGK-EU 涉及的国家（如果不存在）
-- ============================================================
INSERT IGNORE INTO dim_country (code, name, currency) VALUES
('FR', '法国', 'EUR'),
('ES', '西班牙', 'EUR'),
('IT', '意大利', 'EUR'),
('NL', '荷兰', 'EUR'),
('SE', '瑞典', 'SEK'),
('BE', '比利时', 'EUR'),
('IE', '爱尔兰', 'EUR'),
('AE', '阿联酋', 'AED'),
('SA', '沙特', 'SAR');

-- ============================================================
-- 2. dim_exchange_rate 新增汇率（2026-05，仅缺失的）
-- 使用 INSERT IGNORE 避免重复
-- ============================================================
-- ES=8, IT=9, SE=14, BE=16, SA=19, AE=20, IE=23
INSERT IGNORE INTO dim_exchange_rate (country_id, year_month, rate) VALUES
(8,  '2026-05', 7.6200),   -- ES
(9,  '2026-05', 7.6200),   -- IT
(14, '2026-05', 0.6500),   -- SE
(16, '2026-05', 7.6200),   -- BE
(19, '2026-05', 1.8100),   -- SA
(20, '2026-05', 1.8600),   -- AE
(23, '2026-05', 7.6200);   -- IE

-- ============================================================
-- 3. dim_product 加字段：cost_rmb, weight, store_id
-- ============================================================
ALTER TABLE dim_product
  ADD COLUMN store_id INT DEFAULT NULL AFTER id,
  ADD COLUMN cost_rmb DECIMAL(10,2) DEFAULT 0 AFTER color,
  ADD COLUMN weight DECIMAL(10,4) DEFAULT 0 AFTER cost_rmb;

-- 去掉旧唯一键，建新的 (asin, store_id) 联合唯一键
ALTER TABLE dim_product DROP INDEX asin;
ALTER TABLE dim_product
  ADD UNIQUE KEY uk_asin_store (asin, store_id);

-- ============================================================
-- 4. dim_store 扩展字段
-- ============================================================
ALTER TABLE dim_store
  ADD COLUMN marketplace VARCHAR(50) AFTER name,
  ADD COLUMN region VARCHAR(50) AFTER marketplace;

-- ============================================================
-- 5. 新增 MGK-EU 店铺
-- ============================================================
INSERT IGNORE INTO dim_store (code, name, marketplace, region) VALUES
('MGK-EU', 'MangoKit 欧洲站', 'Amazon', 'EU');

-- ============================================================
-- 6. dim_freight 运费表（产品 × 国家 × 店铺）
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_freight (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,
    country_id INT NOT NULL,
    store_id INT DEFAULT NULL,
    freight_rmb DECIMAL(10,2) NOT NULL COMMENT '单件运费(RMB)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES dim_product(id),
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    UNIQUE KEY uk_product_country_store (product_id, country_id, store_id)
);

-- ============================================================
-- 7. dim_time 扩展
-- ============================================================
INSERT IGNORE INTO dim_time (time_year, time_month, year_month) VALUES
(2026, 5, '2026-05');
