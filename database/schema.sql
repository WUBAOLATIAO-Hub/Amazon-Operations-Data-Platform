-- LMG 数据平台数据库
CREATE DATABASE IF NOT EXISTS lmg_platform DEFAULT CHARSET utf8mb4;
USE lmg_platform;

-- 维度表：国家
CREATE TABLE dim_country (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(5) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    currency VARCHAR(5) NOT NULL,
    exchange_rate DECIMAL(10,4) NOT NULL
);

-- 维度表：产品
CREATE TABLE dim_product (
    id INT PRIMARY KEY AUTO_INCREMENT,
    asin VARCHAR(50) NOT NULL,
    sku VARCHAR(100),
    product_name VARCHAR(500),
    color VARCHAR(50),
    cost_rmb DECIMAL(10,2) DEFAULT 0,
    freight_per_unit DECIMAL(10,2) DEFAULT 0,
    exchange_rate DECIMAL(10,4) DEFAULT NULL,
    UNIQUE KEY uk_asin (asin)
);

-- 维度表：时间
CREATE TABLE dim_time (
    id INT PRIMARY KEY AUTO_INCREMENT,
    time_year INT NOT NULL,
    time_month INT NOT NULL,
    `year_month` VARCHAR(7) NOT NULL UNIQUE
);

-- 事实表：原始交易明细
CREATE TABLE raw_transactions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    transaction_date DATETIME,
    settlement_id VARCHAR(50),
    transaction_type VARCHAR(20),
    order_id VARCHAR(50),
    sku VARCHAR(50),
    description VARCHAR(500),
    quantity INT DEFAULT 0,
    marketplace VARCHAR(20),
    fulfillment VARCHAR(20),
    order_city VARCHAR(100),
    order_state VARCHAR(50),
    order_postal VARCHAR(20),
    tax_collection_model VARCHAR(50),
    product_sales DECIMAL(12,2) DEFAULT 0,
    product_sales_tax DECIMAL(12,2) DEFAULT 0,
    shipping_credits DECIMAL(12,2) DEFAULT 0,
    shipping_credits_tax DECIMAL(12,2) DEFAULT 0,
    gift_wrap_credits DECIMAL(12,2) DEFAULT 0,
    giftwrap_credits_tax DECIMAL(12,2) DEFAULT 0,
    regulatory_fee DECIMAL(12,2) DEFAULT 0,
    tax_on_regulatory_fee DECIMAL(12,2) DEFAULT 0,
    promotional_rebates DECIMAL(12,2) DEFAULT 0,
    promotional_rebates_tax DECIMAL(12,2) DEFAULT 0,
    marketplace_withheld_tax DECIMAL(12,2) DEFAULT 0,
    selling_fee DECIMAL(12,2) DEFAULT 0,
    fba_fee DECIMAL(12,2) DEFAULT 0,
    other_transaction_fee DECIMAL(12,2) DEFAULT 0,
    other_amount DECIMAL(12,2) DEFAULT 0,
    total DECIMAL(12,2) DEFAULT 0,
    transaction_status VARCHAR(20),
    transaction_release_date DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_date (transaction_date),
    INDEX idx_sku (sku),
    INDEX idx_order (order_id),
    INDEX idx_country_date (country_id, transaction_date)
);

-- 事实表：月度汇总
CREATE TABLE monthly_summary (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    product_id INT NOT NULL,
    time_id INT NOT NULL,
    product_sales_usd DECIMAL(12,2) DEFAULT 0,
    commission_usd DECIMAL(12,2) DEFAULT 0,
    fba_fee_usd DECIMAL(12,2) DEFAULT 0,
    amazon_payout_usd DECIMAL(12,2) DEFAULT 0,
    product_cost_rmb DECIMAL(12,2) DEFAULT 0,
    freight_cost_rmb DECIMAL(12,2) DEFAULT 0,
    ad_spend_usd DECIMAL(12,2) DEFAULT 0,
    storage_fee_usd DECIMAL(12,2) DEFAULT 0,
    returns_fee_usd DECIMAL(12,2) DEFAULT 0,
    inbound_fee_usd DECIMAL(12,2) DEFAULT 0,
    exchange_rate DECIMAL(10,4) DEFAULT 0,
    product_sales_rmb DECIMAL(12,2) DEFAULT 0,
    net_profit_rmb DECIMAL(12,2) DEFAULT 0,
    net_profit_rate DECIMAL(8,4) DEFAULT 0,
    order_count INT DEFAULT 0,
    order_qty INT DEFAULT 0,
    ad_sales_usd DECIMAL(12,2) DEFAULT 0,
    acos DECIMAL(8,4) DEFAULT 0,
    roas DECIMAL(8,4) DEFAULT 0,
    ctr DECIMAL(8,4) DEFAULT 0,
    cpc DECIMAL(8,4) DEFAULT 0,
    impressions INT DEFAULT 0,
    clicks INT DEFAULT 0,
    ad_orders INT DEFAULT 0,
    conversion_rate DECIMAL(8,4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    FOREIGN KEY (product_id) REFERENCES dim_product(id),
    FOREIGN KEY (time_id) REFERENCES dim_time(id),
    UNIQUE KEY uk_summary (country_id, product_id, time_id)
);

-- 原始数据表：广告数据
CREATE TABLE raw_advertising (
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

-- 原始数据表：月度仓储费
CREATE TABLE raw_storage_fee (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    asin VARCHAR(50),
    fnsku VARCHAR(50),
    product_name VARCHAR(500),
    fulfillment_center VARCHAR(20),
    country_code VARCHAR(50),
    longest_side DECIMAL(10,4) DEFAULT 0,
    median_side DECIMAL(10,4) DEFAULT 0,
    shortest_side DECIMAL(10,4) DEFAULT 0,
    measurement_units VARCHAR(50),
    weight DECIMAL(10,4) DEFAULT 0,
    weight_units VARCHAR(50),
    item_volume DECIMAL(12,6) DEFAULT 0,
    volume_units VARCHAR(50),
    product_size_tier VARCHAR(50),
    average_quantity_on_hand DECIMAL(10,2) DEFAULT 0,
    average_quantity_pending_removal DECIMAL(10,2) DEFAULT 0,
    estimated_total_item_volume DECIMAL(12,6) DEFAULT 0,
    month_of_charge VARCHAR(20),
    storage_utilization_ratio DECIMAL(10,2) DEFAULT 0,
    storage_utilization_ratio_units VARCHAR(50),
    base_rate DECIMAL(10,4) DEFAULT 0,
    utilization_surcharge_rate DECIMAL(10,4) DEFAULT 0,
    avg_qty_for_sus DECIMAL(10,2) DEFAULT 0,
    est_vol_for_sus DECIMAL(12,6) DEFAULT 0,
    est_base_msf DECIMAL(12,4) DEFAULT 0,
    est_sus DECIMAL(12,4) DEFAULT 0,
    currency VARCHAR(10),
    estimated_monthly_storage_fee DECIMAL(12,4) DEFAULT 0,
    dangerous_goods_storage_type VARCHAR(100),
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

-- 原始数据表：退货处理费
CREATE TABLE raw_returns (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    asin VARCHAR(50),
    asin_fee_category VARCHAR(100),
    fnsku VARCHAR(50),
    product_name VARCHAR(500),
    longest_side DECIMAL(10,4) DEFAULT 0,
    median_side DECIMAL(10,4) DEFAULT 0,
    shortest_side DECIMAL(10,4) DEFAULT 0,
    measurement_units VARCHAR(50),
    unit_weight DECIMAL(10,4) DEFAULT 0,
    dimensional_weight DECIMAL(10,4) DEFAULT 0,
    shipping_weight DECIMAL(10,4) DEFAULT 0,
    weight_units VARCHAR(50),
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

-- 原始数据表：入库配置费
CREATE TABLE raw_inbound (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    country_id INT NOT NULL,
    transaction_date DATETIME,
    inbound_plan_id VARCHAR(100),
    fba_shipment_id VARCHAR(50),
    country_region VARCHAR(50),
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
    weight_unit VARCHAR(50),
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

-- 原始数据表：长期仓储费
CREATE TABLE raw_long_term_storage (
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
    volume_unit VARCHAR(50),
    country VARCHAR(50),
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

-- 初始数据
INSERT INTO dim_country (code, name, currency, exchange_rate) VALUES
('US', '美国', 'USD', 6.8000),
('DE', '德国', 'EUR', 8.0000),
('UK', '英国', 'GBP', 9.2300);

INSERT INTO dim_time (time_year, time_month, `year_month`) VALUES
(2026, 1, '2026-01'), (2026, 2, '2026-02'), (2026, 3, '2026-03'),
(2026, 4, '2026-04'), (2026, 5, '2026-05'), (2026, 6, '2026-06'),
(2026, 7, '2026-07'), (2026, 8, '2026-08'), (2026, 9, '2026-09'),
(2026, 10, '2026-10'), (2026, 11, '2026-11'), (2026, 12, '2026-12');
