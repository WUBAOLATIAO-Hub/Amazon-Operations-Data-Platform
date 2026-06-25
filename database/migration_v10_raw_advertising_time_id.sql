-- v10: raw_advertising 加 time_id，支持按月清空
ALTER TABLE raw_advertising ADD COLUMN time_id INT NULL;
