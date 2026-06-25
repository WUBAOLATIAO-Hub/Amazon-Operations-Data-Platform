-- ===================================================================
-- ⚠️ 此文件已过时（缺少多张表和几十个字段）
--   新环境请按序执行: migration_v*.sql
--   本文件仅保留种子数据参考。
-- ===================================================================
DROP DATABASE IF EXISTS lmg_platform;
CREATE DATABASE lmg_platform;
USE lmg_platform;

CREATE TABLE dim_country (id INT AUTO_INCREMENT PRIMARY KEY, code VARCHAR(5) UNIQUE NOT NULL, name VARCHAR(50), currency VARCHAR(5));
INSERT INTO dim_country VALUES (1,'US','美国站','USD'),(2,'UK','英国站','GBP'),(3,'DE','德国站','EUR');

CREATE TABLE dim_exchange_rate (id INT AUTO_INCREMENT PRIMARY KEY, country_id INT, `year_month` VARCHAR(7), rate DECIMAL(10,4), UNIQUE KEY uk_country_month (country_id, `year_month`));
INSERT INTO dim_exchange_rate (country_id, `year_month`, rate) VALUES (1,'2026-05',6.8),(1,'2026-04',6.9),(2,'2026-05',8.8),(3,'2026-05',7.4);

CREATE TABLE dim_product (id INT AUTO_INCREMENT PRIMARY KEY, asin VARCHAR(50) UNIQUE, sku VARCHAR(100), product_name VARCHAR(500), color VARCHAR(50));
CREATE TABLE dim_product_cost (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT, ym VARCHAR(7), cost_rmb DECIMAL(10,2), freight_per_unit DECIMAL(10,2));
CREATE TABLE dim_store (id INT AUTO_INCREMENT PRIMARY KEY, code VARCHAR(50) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE dim_time (id INT AUTO_INCREMENT PRIMARY KEY, time_year INT, time_month INT, `year_month` VARCHAR(7) UNIQUE);

CREATE TABLE monthly_summary (
  id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, product_id INT, time_id INT, store_id INT,
  product_sales_usd DECIMAL(12,2), commission_usd DECIMAL(12,2), fba_fee_usd DECIMAL(12,2),
  product_sales_rmb DECIMAL(12,2), ad_spend_usd DECIMAL(12,2), storage_fee_usd DECIMAL(12,2),
  returns_fee_usd DECIMAL(12,2), inbound_fee_usd DECIMAL(12,2),
  product_cost_rmb DECIMAL(12,2), freight_cost_rmb DECIMAL(12,2),
  amazon_payout_usd DECIMAL(12,2),
  net_profit_rmb DECIMAL(12,2), net_profit_rate DECIMAL(8,4),
  order_count INT, order_qty INT, exchange_rate DECIMAL(10,4),
  ad_sales_usd DECIMAL(12,2), acos DECIMAL(8,4), roas DECIMAL(8,4),
  ctr DECIMAL(8,4), cpc DECIMAL(8,4), impressions INT,
  clicks INT, ad_orders INT, conversion_rate DECIMAL(8,4)
);

CREATE TABLE raw_transactions (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, transaction_date DATETIME, transaction_type VARCHAR(80), order_id VARCHAR(50), sku VARCHAR(100), description VARCHAR(500), quantity INT, marketplace VARCHAR(20), fulfillment VARCHAR(20), product_sales DECIMAL(12,2), selling_fee DECIMAL(12,2), fba_fee DECIMAL(12,2), shipping_credits DECIMAL(12,2), promotional_rebates DECIMAL(12,2), gift_wrap_credits DECIMAL(12,2), total DECIMAL(12,2));
CREATE TABLE raw_advertising (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, asin VARCHAR(50), product_field VARCHAR(200), status_val VARCHAR(50), ad_type VARCHAR(50), eligibility VARCHAR(100), sales_usd DECIMAL(12,2), roas DECIMAL(10,4), conversion_rate DECIMAL(10,4), impressions INT, clicks INT, ctr DECIMAL(10,4), spend_usd DECIMAL(12,2), cpc DECIMAL(10,4), orders INT, acos DECIMAL(10,4), ntb_orders INT, ntb_order_pct DECIMAL(10,4), ntb_sales_usd DECIMAL(12,2), new_to_brand_sales_pct DECIMAL(10,4), visible_impressions INT);
CREATE TABLE raw_storage_fee (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, asin VARCHAR(50), estimated_monthly_storage_fee DECIMAL(12,4), month_of_charge VARCHAR(20));
CREATE TABLE raw_returns (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, asin VARCHAR(50), sku_returns_fee DECIMAL(12,4));
CREATE TABLE raw_inbound (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, asin VARCHAR(50), inbound_placement_fee_total DECIMAL(12,4));
CREATE TABLE raw_long_term_storage (id BIGINT AUTO_INCREMENT PRIMARY KEY, country_id INT, store_id INT, asin VARCHAR(50), amount_charged DECIMAL(12,4));
