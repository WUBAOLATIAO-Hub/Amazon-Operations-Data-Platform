-- =========================================================
-- Migration v10: 修复 P0-4
-- raw_advertising / raw_long_term_storage 添加 time_id 字段
-- 解决"每次导入广告全店清空导致历史月份丢失"问题
--
-- 执行方式:
--   mysql -uroot lmg_platform < migration_v10_advertising_time.sql
-- 回退方式:
--   ALTER TABLE raw_advertising DROP FOREIGN KEY fk_adv_time;
--   ALTER TABLE raw_advertising DROP INDEX idx_adv_store_time;
--   ALTER TABLE raw_advertising DROP COLUMN time_id;
--   (raw_long_term_storage 同理)
-- =========================================================

-- 1. raw_advertising 加 time_id
ALTER TABLE raw_advertising
    ADD COLUMN time_id INT NULL AFTER store_id;

ALTER TABLE raw_advertising
    ADD CONSTRAINT fk_adv_time FOREIGN KEY (time_id) REFERENCES dim_time(id);

ALTER TABLE raw_advertising
    ADD INDEX idx_adv_store_time (store_id, time_id);

-- 2. raw_long_term_storage 加 time_id
ALTER TABLE raw_long_term_storage
    ADD COLUMN time_id INT NULL AFTER store_id;

ALTER TABLE raw_long_term_storage
    ADD CONSTRAINT fk_lts_time FOREIGN KEY (time_id) REFERENCES dim_time(id);

ALTER TABLE raw_long_term_storage
    ADD INDEX idx_lts_store_time (store_id, time_id);

-- 3. 回填现有数据 time_id = 2026-05（最近一次导入月份）
-- 这批数据本来就只有"最近一次"导入的，回填月份再准也没历史可保留
UPDATE raw_advertising a
JOIN dim_time t ON t.year_month = '2026-05'
SET a.time_id = t.id
WHERE a.time_id IS NULL;

UPDATE raw_long_term_storage l
JOIN dim_time t ON t.year_month = '2026-05'
SET l.time_id = t.id
WHERE l.time_id IS NULL;

-- 4. 验证
SELECT '=== 广告表 ===' AS info;
SELECT COUNT(*) AS total,
       SUM(CASE WHEN time_id IS NULL THEN 1 ELSE 0 END) AS null_time_id
FROM raw_advertising;

SELECT '=== 长期仓储费表 ===' AS info;
SELECT COUNT(*) AS total,
       SUM(CASE WHEN time_id IS NULL THEN 1 ELSE 0 END) AS null_time_id
FROM raw_long_term_storage;
