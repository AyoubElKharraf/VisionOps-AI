-- VisionOps AI — PostgreSQL bootstrap
-- Extends visionops_db with schemas used in later phases.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS visionops;

COMMENT ON SCHEMA visionops IS 'VisionOps AI application schema (cameras, alerts, ROI)';
