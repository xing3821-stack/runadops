-- runadops 操盘控制台 · 自建后端建表脚本(MySQL 8)
-- 跑一次:  mysql < schema.sql
-- 和原来 Supabase 那套结构一致,只是多了 pw_hash(自己管登录)和 sessions。

CREATE DATABASE IF NOT EXISTS runadops
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE runadops;

-- 账号与角色
CREATE TABLE IF NOT EXISTS profiles (
  id         CHAR(36)     NOT NULL PRIMARY KEY,
  email      VARCHAR(255) NOT NULL UNIQUE,
  name       VARCHAR(100),
  role       ENUM('owner','admin','member') NOT NULL DEFAULT 'member',
  pw_hash    VARCHAR(255) NOT NULL,
  created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 全部业务数据:type 区分种类,data 存具体字段
--   client 客户 / campaign 投放项目 / payment 收款 / package 套餐
--   brief 投放方案 / settings 全站配置
CREATE TABLE IF NOT EXISTS records (
  id         CHAR(36)    NOT NULL PRIMARY KEY,
  type       VARCHAR(32) NOT NULL,
  data       JSON        NOT NULL,
  updated_at TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  updated_by CHAR(36),
  KEY records_type_idx (type),
  KEY records_updated_idx (updated_at)
) ENGINE=InnoDB;

-- 登录会话(cookie 里那个随机串)
CREATE TABLE IF NOT EXISTS sessions (
  token      CHAR(64)  NOT NULL PRIMARY KEY,
  user_id    CHAR(36)  NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  KEY sessions_user_idx (user_id),
  KEY sessions_exp_idx (expires_at),
  CONSTRAINT sessions_user_fk FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
) ENGINE=InnoDB;
