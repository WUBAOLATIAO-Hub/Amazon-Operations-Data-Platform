-- LMG 数据平台 v3 迁移脚本
-- 新增：全量原始数据存储
-- 执行方式：mysql -u root -p lmg_platform < migration_v3.sql

USE lmg_platform;

-- 1. dim_product: 放宽 ASIN 长度，新增 exchange_rate
ALTER TABLE dim_product MODIFY COLUMN asin VARCHAR(50) NOT NULL;
ALTER TABLE dim_product MODIFY COLUMN sku VARCHAR(100);
ALTER TABLE dim_product ADD COLUMN exchange_rate DECIMAL(10,4) DEFAULT NULL AFTER freight_per_unit;

-- 2. raw_advertising: 广告原始数据
CREATE TABLE IF NOT EXISTS raw_advertising (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    product_field VARCHAR(200),
    asin VARCHAR(50),
    status_val VARCHAR(50),
    ad_type VARCHAR(50),
    eligibility VARCHAR(100),
    sales_usd DECIMAL(12,2) DEFAULT 0,
    roas DECIMAL(10,4) DEFAULT 0,
    conversion_rate DECIMAL(10,4) DEFAULT 0,
    impressions INT DEFAULT 0,
    clicks INT DEFAULT 0,
    ctr DECIMAL(10,4) DEFAULT 0,
    spend_usd DECIMAL(12,2) DEFAULT 0,
    cpc DECIMAL(10,4) DEFAULT 0,
    orders INT DEFAULT 0,
    acos DECIMAL(10,4) DEFAULT 0,
    ntb_orders INT DEFAULT 0,
    ntb_order_pct DECIMAL(10,4) DEFAULT 0,
    ntb_sales_usd DECIMAL(12,2) DEFAULT 0,
    new_to_brand_sales_pct DECIMAL(10,4) DEFAULT 0,
    visible_impressions INT DEFAULT 0,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_asin (asin),
    INDEX idx_country (country_id)
);

-- 3. raw_storage_fee: 月度仓储费原始数据
CREATE TABLE IF NOT EXISTS raw_storage_fee (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    asin VARCHAR(50),
    fnsku VARCHAR(50),
    product_name VARCHAR(500),
    fulfillment_center VARCHAR(20),
    country_code VARCHAR(10),
    longest_side DECIMAL(10,4) DEFAULT 0,
    median_side DECIMAL(10,4) DEFAULT 0,
    shortest_side DECIMAL(10,4) DEFAULT 0,
    measurement_units VARCHAR(20),
    weight DECIMAL(10,4) DEFAULT 0,
    weight_units VARCHAR(20),
    item_volume DECIMAL(12,6) DEFAULT 0,
    volume_units VARCHAR(20),
    product_size_tier VARCHAR(50),
    average_quantity_on_hand DECIMAL(10,2) DEFAULT 0,
    average_quantity_pending_removal DECIMAL(10,2) DEFAULT 0,
    estimated_total_item_volume DECIMAL(12,6) DEFAULT 0,
    month_of_charge VARCHAR(20),
    storage_utilization_ratio DECIMAL(10,2) DEFAULT 0,
    storage_utilization_ratio_units VARCHAR(20),
    base_rate DECIMAL(10,4) DEFAULT 0,
    utilization_surcharge_rate DECIMAL(10,4) DEFAULT 0,
    avg_qty_for_sus DECIMAL(10,2) DEFAULT 0,
    est_vol_for_sus DECIMAL(12,6) DEFAULT 0,
    est_base_msf DECIMAL(12,4) DEFAULT 0,
    est_sus DECIMAL(12,4) DEFAULT 0,
    currency VARCHAR(10),
    estimated_monthly_storage_fee DECIMAL(12,4) DEFAULT 0,
    dangerous_goods_storage_type VARCHAR(50),
    eligible_for_inventory_discount VARCHAR(10),
    qualifies_for_inventory_discount VARCHAR(10),
    total_incentive_fee_amount DECIMAL(12,4) DEFAULT 0,
    breakdown_incentive_fee_amount DECIMAL(12,4) DEFAULT 0,
    average_quantity_customer_orders DECIMAL(10,2) DEFAULT 0,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_asin (asin),
    INDEX idx_country (country_id)
);

-- 4. raw_returns: 退货处理费原始数据
CREATE TABLE IF NOT EXISTS raw_returns (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    asin VARCHAR(50),
    asin_fee_category VARCHAR(100),
    fnsku VARCHAR(50),
    product_name VARCHAR(500),
    longest_side DECIMAL(10,4) DEFAULT 0,
    median_side DECIMAL(10,4) DEFAULT 0,
    shortest_side DECIMAL(10,4) DEFAULT 0,
    measurement_units VARCHAR(20),
    unit_weight DECIMAL(10,4) DEFAULT 0,
    dimensional_weight DECIMAL(10,4) DEFAULT 0,
    shipping_weight DECIMAL(10,4) DEFAULT 0,
    weight_units VARCHAR(20),
    sku_sizetier VARCHAR(50),
    month_of_shipment VARCHAR(20),
    asin_shipped_units INT DEFAULT 0,
    asin_return_threshold_percent DECIMAL(10,4) DEFAULT 0,
    asin_return_threshold_units INT DEFAULT 0,
    asin_returned_units INT DEFAULT 0,
    sku_returned_units_nsp_exempted INT DEFAULT 0,
    sku_returned_units_charged INT DEFAULT 0,
    sku_fee_per_unit DECIMAL(10,4) DEFAULT 0,
    sku_returns_fee DECIMAL(12,4) DEFAULT 0,
    month_of_charge VARCHAR(20),
    currency VARCHAR(10),
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_asin (asin),
    INDEX idx_country (country_id)
);

-- 5. raw_inbound: 入库配置费原始数据
CREATE TABLE IF NOT EXISTS raw_inbound (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    transaction_date DATETIME,
    inbound_plan_id VARCHAR(100),
    fba_shipment_id VARCHAR(50),
    country_region VARCHAR(20),
    fnsku VARCHAR(50),
    asin VARCHAR(50),
    planned_inbound_service VARCHAR(100),
    planned_shipment_qty INT DEFAULT 0,
    eligible_shipment_qty INT DEFAULT 0,
    inbound_defect_type VARCHAR(100),
    actual_fee_segment VARCHAR(100),
    planned_inbound_region VARCHAR(50),
    actual_inbound_region VARCHAR(50),
    actual_received_qty INT DEFAULT 0,
    product_size_segment VARCHAR(50),
    shipping_weight DECIMAL(10,4) DEFAULT 0,
    weight_unit VARCHAR(20),
    inbound_placement_fee_rate DECIMAL(10,4) DEFAULT 0,
    eligible_actual_incentive DECIMAL(12,4) DEFAULT 0,
    currency VARCHAR(10),
    inbound_placement_fee_total DECIMAL(12,4) DEFAULT 0,
    total_fee DECIMAL(12,4) DEFAULT 0,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_asin (asin),
    INDEX idx_country (country_id)
);

-- 6. raw_long_term_storage: 长期仓储费原始数据
CREATE TABLE IF NOT EXISTS raw_long_term_storage (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    snapshot_date VARCHAR(30),
    sku VARCHAR(100),
    fnsku VARCHAR(50),
    asin VARCHAR(50),
    product_name VARCHAR(500),
    condition_val VARCHAR(50),
    per_unit_volume DECIMAL(12,6) DEFAULT 0,
    currency VARCHAR(10),
    volume_unit VARCHAR(20),
    country VARCHAR(20),
    qty_charged INT DEFAULT 0,
    amount_charged DECIMAL(12,4) DEFAULT 0,
    surcharge_age_tier VARCHAR(50),
    rate_surcharge DECIMAL(10,4) DEFAULT 0,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_asin (asin),
    INDEX idx_country (country_id)
);

-- 完成
SELECT 'Migration v3 完成' AS status;
