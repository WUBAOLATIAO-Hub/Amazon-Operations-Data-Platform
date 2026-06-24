-- =========================================================
-- LMG 数据平台 — 权威建库脚本 (schema_v10_full)
-- 生成日期: 2026-06-24
-- 来源: 从生产库 mysqldump --no-data 导出
--
-- 部署流程:
--   1. mysql -uroot -e "CREATE DATABASE IF NOT EXISTS lmg_platform DEFAULT CHARSET utf8mb4"
--   2. mysql -uroot lmg_platform < schema_v10_full.sql
--   3. 启动后端: uvicorn main:app
--   4. 后端 seed_admin 会自动创建 admin/123456 账号
--
-- 已废弃 (DO NOT USE):
--   schema.sql      → 缺 store_id、缺多个 v3-v9 字段
--   init.sql        → DROP DATABASE 无 IF EXISTS，危险
--
-- 已有环境升级请按版本号顺序执行 migration_v*.sql:
--   v3 → v5 → v6 → v7 → v8 → v9 → v10
-- =========================================================


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `dim_country`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_country` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(5) NOT NULL,
  `name` varchar(50) NOT NULL,
  `currency` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_exchange_rate`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_exchange_rate` (
  `id` int NOT NULL AUTO_INCREMENT,
  `store_id` int DEFAULT NULL,
  `country_id` int NOT NULL,
  `year_month` varchar(7) NOT NULL,
  `rate` decimal(10,4) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `store_id` (`store_id`),
  KEY `country_id` (`country_id`),
  CONSTRAINT `dim_exchange_rate_ibfk_1` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`),
  CONSTRAINT `dim_exchange_rate_ibfk_2` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2116 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_freight`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_freight` (
  `id` int NOT NULL AUTO_INCREMENT,
  `product_id` int NOT NULL,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `freight_rmb` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `product_id` (`product_id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  CONSTRAINT `dim_freight_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `dim_product` (`id`),
  CONSTRAINT `dim_freight_ibfk_2` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `dim_freight_ibfk_3` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=39431 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_product`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_product` (
  `id` int NOT NULL AUTO_INCREMENT,
  `asin` varchar(50) NOT NULL,
  `sku` varchar(100) DEFAULT NULL,
  `product_name` varchar(500) DEFAULT NULL,
  `color` varchar(50) DEFAULT NULL,
  `store_id` int DEFAULT NULL,
  `year_month` varchar(7) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_store_month_asin` (`store_id`,`year_month`,`asin`)
) ENGINE=InnoDB AUTO_INCREMENT=4844 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_product_cost`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_product_cost` (
  `id` int NOT NULL AUTO_INCREMENT,
  `product_id` int NOT NULL,
  `year_month` varchar(7) NOT NULL,
  `cost_rmb` decimal(10,2) DEFAULT NULL,
  `freight_per_unit` decimal(10,2) DEFAULT NULL,
  `exchange_rate` decimal(10,4) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `dim_product_cost_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `dim_product` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5397 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_store`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_store` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `dim_time`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `dim_time` (
  `id` int NOT NULL AUTO_INCREMENT,
  `time_year` int NOT NULL,
  `time_month` int NOT NULL,
  `year_month` varchar(7) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `year_month` (`year_month`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `monthly_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `monthly_summary` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `product_id` int NOT NULL,
  `time_id` int NOT NULL,
  `product_sales_usd` decimal(12,2) DEFAULT NULL,
  `commission_usd` decimal(12,2) DEFAULT NULL,
  `fba_fee_usd` decimal(12,2) DEFAULT NULL,
  `shipping_credits_usd` decimal(12,2) DEFAULT NULL,
  `giftwrap_credits_usd` decimal(12,2) DEFAULT NULL,
  `postage_credits_usd` decimal(12,2) DEFAULT NULL,
  `amazon_payout_usd` decimal(12,2) DEFAULT NULL,
  `product_cost_rmb` decimal(12,2) DEFAULT NULL,
  `freight_cost_rmb` decimal(12,2) DEFAULT NULL,
  `ad_spend_usd` decimal(12,2) DEFAULT NULL,
  `storage_fee_usd` decimal(12,2) DEFAULT NULL,
  `returns_fee_usd` decimal(12,2) DEFAULT NULL,
  `inbound_fee_usd` decimal(12,2) DEFAULT NULL,
  `removal_fee_usd` decimal(12,2) DEFAULT NULL,
  `promo_rebate_usd` decimal(12,2) DEFAULT NULL,
  `promo_rebate_tax_usd` decimal(12,2) DEFAULT NULL,
  `marketplace_withheld_tax_usd` decimal(12,2) DEFAULT NULL,
  `product_sales_tax_usd` decimal(12,2) DEFAULT NULL,
  `shipping_credits_tax_usd` decimal(12,2) DEFAULT NULL,
  `giftwrap_credits_tax_usd` decimal(12,2) DEFAULT NULL,
  `adjustment_usd` decimal(12,2) DEFAULT NULL,
  `other_fee_usd` decimal(12,2) DEFAULT NULL,
  `other_amount_usd` decimal(12,2) DEFAULT NULL,
  `exchange_rate` decimal(10,4) DEFAULT NULL,
  `product_sales_rmb` decimal(12,2) DEFAULT NULL,
  `net_profit_rmb` decimal(12,2) DEFAULT NULL,
  `net_profit_rate` decimal(8,4) DEFAULT NULL,
  `order_count` int DEFAULT NULL,
  `order_qty` int DEFAULT NULL,
  `ad_sales_usd` decimal(12,2) DEFAULT NULL,
  `acos` decimal(8,4) DEFAULT NULL,
  `roas` decimal(8,4) DEFAULT NULL,
  `ctr` decimal(8,4) DEFAULT NULL,
  `cpc` decimal(8,4) DEFAULT NULL,
  `impressions` int DEFAULT NULL,
  `clicks` int DEFAULT NULL,
  `ad_orders` int DEFAULT NULL,
  `conversion_rate` decimal(8,4) DEFAULT NULL,
  `postage_credits` decimal(12,2) DEFAULT '0.00',
  `product_sales_tax` decimal(12,2) DEFAULT '0.00',
  `shipping_credits_tax` decimal(12,2) DEFAULT '0.00',
  `gift_wrap_credits` decimal(12,2) DEFAULT '0.00',
  `giftwrap_credits_tax` decimal(12,2) DEFAULT '0.00',
  `shipping_credits` decimal(12,2) DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  KEY `product_id` (`product_id`),
  KEY `time_id` (`time_id`),
  CONSTRAINT `monthly_summary_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `monthly_summary_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`),
  CONSTRAINT `monthly_summary_ibfk_3` FOREIGN KEY (`product_id`) REFERENCES `dim_product` (`id`),
  CONSTRAINT `monthly_summary_ibfk_4` FOREIGN KEY (`time_id`) REFERENCES `dim_time` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=89405 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_advertising`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_advertising` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `time_id` int DEFAULT NULL,
  `product_field` varchar(200) DEFAULT NULL,
  `asin` varchar(50) DEFAULT NULL,
  `status_val` varchar(50) DEFAULT NULL,
  `ad_type` varchar(50) DEFAULT NULL,
  `eligibility` varchar(100) DEFAULT NULL,
  `sales_usd` decimal(12,2) DEFAULT NULL,
  `roas` decimal(10,4) DEFAULT NULL,
  `conversion_rate` decimal(10,4) DEFAULT NULL,
  `impressions` int DEFAULT NULL,
  `clicks` int DEFAULT NULL,
  `ctr` decimal(10,4) DEFAULT NULL,
  `spend_usd` decimal(12,2) DEFAULT NULL,
  `cpc` decimal(10,4) DEFAULT NULL,
  `orders` int DEFAULT NULL,
  `acos` decimal(10,4) DEFAULT NULL,
  `ntb_orders` int DEFAULT NULL,
  `ntb_order_pct` decimal(10,4) DEFAULT NULL,
  `ntb_sales_usd` decimal(12,2) DEFAULT NULL,
  `new_to_brand_sales_pct` decimal(10,4) DEFAULT NULL,
  `visible_impressions` int DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `fk_adv_time` (`time_id`),
  KEY `idx_adv_store_time` (`store_id`,`time_id`),
  CONSTRAINT `fk_adv_time` FOREIGN KEY (`time_id`) REFERENCES `dim_time` (`id`),
  CONSTRAINT `raw_advertising_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_advertising_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=36627 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_inbound`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_inbound` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `transaction_date` datetime DEFAULT NULL,
  `inbound_plan_id` varchar(100) DEFAULT NULL,
  `fba_shipment_id` varchar(50) DEFAULT NULL,
  `country_region` varchar(50) DEFAULT NULL,
  `fnsku` varchar(50) DEFAULT NULL,
  `asin` varchar(50) DEFAULT NULL,
  `planned_inbound_service` varchar(100) DEFAULT NULL,
  `planned_shipment_qty` int DEFAULT NULL,
  `eligible_shipment_qty` int DEFAULT NULL,
  `inbound_defect_type` varchar(100) DEFAULT NULL,
  `actual_fee_segment` varchar(100) DEFAULT NULL,
  `planned_inbound_region` varchar(50) DEFAULT NULL,
  `actual_inbound_region` varchar(50) DEFAULT NULL,
  `actual_received_qty` int DEFAULT NULL,
  `product_size_segment` varchar(50) DEFAULT NULL,
  `shipping_weight` decimal(10,4) DEFAULT NULL,
  `weight_unit` varchar(50) DEFAULT NULL,
  `inbound_placement_fee_rate` decimal(10,4) DEFAULT NULL,
  `eligible_actual_incentive` decimal(12,4) DEFAULT NULL,
  `currency` varchar(10) DEFAULT NULL,
  `inbound_placement_fee_total` decimal(12,4) DEFAULT NULL,
  `total_fee` decimal(12,4) DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  CONSTRAINT `raw_inbound_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_inbound_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6471 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_long_term_storage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_long_term_storage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `time_id` int DEFAULT NULL,
  `snapshot_date` varchar(30) DEFAULT NULL,
  `sku` varchar(100) DEFAULT NULL,
  `fnsku` varchar(50) DEFAULT NULL,
  `asin` varchar(50) DEFAULT NULL,
  `product_name` varchar(500) DEFAULT NULL,
  `condition_val` varchar(50) DEFAULT NULL,
  `per_unit_volume` decimal(12,6) DEFAULT NULL,
  `currency` varchar(50) DEFAULT NULL,
  `volume_unit` varchar(50) DEFAULT NULL,
  `country` varchar(50) DEFAULT NULL,
  `qty_charged` int DEFAULT NULL,
  `amount_charged` decimal(12,4) DEFAULT NULL,
  `surcharge_age_tier` varchar(50) DEFAULT NULL,
  `rate_surcharge` decimal(10,4) DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `fk_lts_time` (`time_id`),
  KEY `idx_lts_store_time` (`store_id`,`time_id`),
  CONSTRAINT `fk_lts_time` FOREIGN KEY (`time_id`) REFERENCES `dim_time` (`id`),
  CONSTRAINT `raw_long_term_storage_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_long_term_storage_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5347 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_removal_fee`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_removal_fee` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `store_id` int DEFAULT NULL,
  `country_id` int NOT NULL,
  `request_date` datetime DEFAULT NULL,
  `order_id` varchar(50) DEFAULT NULL,
  `order_source` varchar(200) DEFAULT NULL,
  `order_type` varchar(50) DEFAULT NULL,
  `service_speed` varchar(50) DEFAULT NULL,
  `order_status` varchar(50) DEFAULT NULL,
  `last_updated_date` datetime DEFAULT NULL,
  `sku` varchar(100) DEFAULT NULL,
  `fnsku` varchar(50) DEFAULT NULL,
  `disposition` varchar(50) DEFAULT NULL,
  `requested_quantity` int DEFAULT NULL,
  `cancelled_quantity` int DEFAULT NULL,
  `disposed_quantity` int DEFAULT NULL,
  `shipped_quantity` int DEFAULT NULL,
  `in_process_quantity` int DEFAULT NULL,
  `removal_fee` decimal(12,4) DEFAULT NULL,
  `currency` varchar(10) DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `store_id` (`store_id`),
  KEY `country_id` (`country_id`),
  CONSTRAINT `raw_removal_fee_ibfk_1` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`),
  CONSTRAINT `raw_removal_fee_ibfk_2` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5642 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_returns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_returns` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `asin` varchar(50) DEFAULT NULL,
  `asin_fee_category` varchar(100) DEFAULT NULL,
  `fnsku` varchar(50) DEFAULT NULL,
  `product_name` varchar(500) DEFAULT NULL,
  `longest_side` decimal(10,4) DEFAULT NULL,
  `median_side` decimal(10,4) DEFAULT NULL,
  `shortest_side` decimal(10,4) DEFAULT NULL,
  `measurement_units` varchar(50) DEFAULT NULL,
  `unit_weight` decimal(10,4) DEFAULT NULL,
  `dimensional_weight` decimal(10,4) DEFAULT NULL,
  `shipping_weight` decimal(10,4) DEFAULT NULL,
  `weight_units` varchar(50) DEFAULT NULL,
  `sku_sizetier` varchar(50) DEFAULT NULL,
  `month_of_shipment` varchar(20) DEFAULT NULL,
  `asin_shipped_units` int DEFAULT NULL,
  `asin_return_threshold_percent` decimal(10,4) DEFAULT NULL,
  `asin_return_threshold_units` int DEFAULT NULL,
  `asin_returned_units` int DEFAULT NULL,
  `sku_returned_units_nsp_exempted` int DEFAULT NULL,
  `sku_returned_units_charged` int DEFAULT NULL,
  `sku_fee_per_unit` decimal(10,4) DEFAULT NULL,
  `sku_returns_fee` decimal(12,4) DEFAULT NULL,
  `month_of_charge` varchar(20) DEFAULT NULL,
  `currency` varchar(10) DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  CONSTRAINT `raw_returns_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_returns_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=183 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_storage_fee`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_storage_fee` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `asin` varchar(50) DEFAULT NULL,
  `fnsku` varchar(50) DEFAULT NULL,
  `product_name` varchar(500) DEFAULT NULL,
  `fulfillment_center` varchar(20) DEFAULT NULL,
  `country_code` varchar(50) DEFAULT NULL,
  `longest_side` decimal(10,4) DEFAULT NULL,
  `median_side` decimal(10,4) DEFAULT NULL,
  `shortest_side` decimal(10,4) DEFAULT NULL,
  `measurement_units` varchar(50) DEFAULT NULL,
  `weight` decimal(10,4) DEFAULT NULL,
  `weight_units` varchar(50) DEFAULT NULL,
  `item_volume` decimal(12,6) DEFAULT NULL,
  `volume_units` varchar(50) DEFAULT NULL,
  `product_size_tier` varchar(50) DEFAULT NULL,
  `average_quantity_on_hand` decimal(10,2) DEFAULT NULL,
  `average_quantity_pending_removal` decimal(10,2) DEFAULT NULL,
  `estimated_total_item_volume` decimal(12,6) DEFAULT NULL,
  `month_of_charge` varchar(20) DEFAULT NULL,
  `storage_utilization_ratio` decimal(10,2) DEFAULT NULL,
  `storage_utilization_ratio_units` varchar(50) DEFAULT NULL,
  `base_rate` decimal(10,4) DEFAULT NULL,
  `utilization_surcharge_rate` decimal(10,4) DEFAULT NULL,
  `avg_qty_for_sus` decimal(10,2) DEFAULT NULL,
  `est_vol_for_sus` decimal(12,6) DEFAULT NULL,
  `est_base_msf` decimal(12,4) DEFAULT NULL,
  `est_sus` decimal(12,4) DEFAULT NULL,
  `currency` varchar(10) DEFAULT NULL,
  `estimated_monthly_storage_fee` decimal(12,4) DEFAULT NULL,
  `dangerous_goods_storage_type` varchar(100) DEFAULT NULL,
  `eligible_for_inventory_discount` varchar(10) DEFAULT NULL,
  `qualifies_for_inventory_discount` varchar(10) DEFAULT NULL,
  `total_incentive_fee_amount` decimal(12,4) DEFAULT NULL,
  `breakdown_incentive_fee_amount` decimal(12,4) DEFAULT NULL,
  `average_quantity_customer_orders` decimal(10,2) DEFAULT NULL,
  `raw_data` json DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  CONSTRAINT `raw_storage_fee_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_storage_fee_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=372567 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `raw_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `raw_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `country_id` int NOT NULL,
  `store_id` int DEFAULT NULL,
  `time_id` int DEFAULT NULL,
  `transaction_date` datetime DEFAULT NULL,
  `settlement_id` varchar(50) DEFAULT NULL,
  `transaction_type` varchar(80) DEFAULT NULL,
  `order_id` varchar(50) DEFAULT NULL,
  `sku` varchar(50) DEFAULT NULL,
  `description` varchar(500) DEFAULT NULL,
  `quantity` int DEFAULT NULL,
  `marketplace` varchar(20) DEFAULT NULL,
  `fulfillment` varchar(20) DEFAULT NULL,
  `order_city` varchar(100) DEFAULT NULL,
  `order_state` varchar(50) DEFAULT NULL,
  `order_postal` varchar(20) DEFAULT NULL,
  `tax_collection_model` varchar(50) DEFAULT NULL,
  `product_sales` decimal(12,2) DEFAULT NULL,
  `product_sales_tax` decimal(12,2) DEFAULT NULL,
  `shipping_credits` decimal(12,2) DEFAULT NULL,
  `shipping_credits_tax` decimal(12,2) DEFAULT NULL,
  `postage_credits` decimal(12,2) DEFAULT NULL,
  `gift_wrap_credits` decimal(12,2) DEFAULT NULL,
  `giftwrap_credits_tax` decimal(12,2) DEFAULT NULL,
  `regulatory_fee` decimal(12,2) DEFAULT NULL,
  `tax_on_regulatory_fee` decimal(12,2) DEFAULT NULL,
  `promotional_rebates` decimal(12,2) DEFAULT NULL,
  `promotional_rebates_tax` decimal(12,2) DEFAULT NULL,
  `marketplace_withheld_tax` decimal(12,2) DEFAULT NULL,
  `selling_fee` decimal(12,2) DEFAULT NULL,
  `fba_fee` decimal(12,2) DEFAULT NULL,
  `other_transaction_fee` decimal(12,2) DEFAULT NULL,
  `other_amount` decimal(12,2) DEFAULT NULL,
  `total` decimal(12,2) DEFAULT NULL,
  `transaction_status` varchar(20) DEFAULT NULL,
  `transaction_release_date` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `country_id` (`country_id`),
  KEY `store_id` (`store_id`),
  KEY `time_id` (`time_id`),
  CONSTRAINT `raw_transactions_ibfk_1` FOREIGN KEY (`country_id`) REFERENCES `dim_country` (`id`),
  CONSTRAINT `raw_transactions_ibfk_2` FOREIGN KEY (`store_id`) REFERENCES `dim_store` (`id`),
  CONSTRAINT `raw_transactions_ibfk_3` FOREIGN KEY (`time_id`) REFERENCES `dim_time` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=761303 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(200) NOT NULL,
  `is_admin` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

