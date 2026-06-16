-- Migration v9: 添加移除费支持
-- 执行方式: mysql -u root -p lmg_platform < migration_v9_removal_fee.sql

-- 1. 创建移除费原始数据表
CREATE TABLE IF NOT EXISTS raw_removal_fee (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    store_id INT DEFAULT NULL,
    country_id INT NOT NULL,
    request_date DATETIME,
    order_id VARCHAR(50),
    order_source VARCHAR(200),
    order_type VARCHAR(50),
    service_speed VARCHAR(50),
    order_status VARCHAR(50),
    last_updated_date DATETIME,
    sku VARCHAR(100),
    fnsku VARCHAR(50),
    disposition VARCHAR(50),
    requested_quantity INT DEFAULT 0,
    cancelled_quantity INT DEFAULT 0,
    disposed_quantity INT DEFAULT 0,
    shipped_quantity INT DEFAULT 0,
    in_process_quantity INT DEFAULT 0,
    removal_fee DECIMAL(12,4) DEFAULT 0,
    currency VARCHAR(10),
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES dim_country(id),
    INDEX idx_sku (sku),
    INDEX idx_country (country_id),
    INDEX idx_order (order_id),
    INDEX idx_date (request_date)
);

-- 2. monthly_summary 添加移除费字段
ALTER TABLE monthly_summary
    ADD COLUMN removal_fee_usd DECIMAL(12,2) DEFAULT 0 AFTER inbound_fee_usd;

-- 验证
SELECT 'raw_removal_fee 表已创建' AS status;
SELECT 'monthly_summary.removal_fee_usd 列已添加' AS status;
