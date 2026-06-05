-- Argus triage database schema.
--
-- One row per (error_code, component_id, operation_id, environment).
-- Status changes are append-only via status_history, populated by triggers.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS codes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    error_code              TEXT NOT NULL,
    component_id            TEXT NOT NULL,
    operation_id            TEXT NOT NULL,
    environment             TEXT NOT NULL,
    classification_code     TEXT,
    responsibility_type     TEXT CHECK (
        responsibility_type IN ('INTERNAL','EXTERNAL','CLIENT','UNKNOWN')
        OR responsibility_type IS NULL
    ),
    category                TEXT,
    supplier                TEXT,
    status                  TEXT NOT NULL DEFAULT 'Assess',
    notes                   TEXT,
    suggested_fix           TEXT,
    related_pr              TEXT,
    related_argus_finding   TEXT,
    first_seen              DATE,
    last_seen               DATE,
    last_reviewed           DATE,
    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(error_code, component_id, operation_id, environment)
);

CREATE INDEX IF NOT EXISTS idx_codes_code        ON codes(error_code);
CREATE INDEX IF NOT EXISTS idx_codes_status      ON codes(status);
CREATE INDEX IF NOT EXISTS idx_codes_environment ON codes(environment);
CREATE INDEX IF NOT EXISTS idx_codes_supplier    ON codes(supplier);
CREATE INDEX IF NOT EXISTS idx_codes_component   ON codes(component_id);

CREATE TABLE IF NOT EXISTS status_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id      INTEGER NOT NULL REFERENCES codes(id) ON DELETE CASCADE,
    old_status   TEXT,
    new_status   TEXT NOT NULL,
    changed_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by   TEXT,
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_code ON status_history(code_id);

CREATE TRIGGER IF NOT EXISTS trg_code_insert
AFTER INSERT ON codes
BEGIN
    INSERT INTO status_history (code_id, old_status, new_status, note)
    VALUES (NEW.id, NULL, NEW.status, 'initial');
END;

CREATE TRIGGER IF NOT EXISTS trg_status_change
AFTER UPDATE OF status ON codes
WHEN OLD.status IS NOT NEW.status
BEGIN
    INSERT INTO status_history (code_id, old_status, new_status)
    VALUES (NEW.id, OLD.status, NEW.status);
END;

CREATE TRIGGER IF NOT EXISTS trg_codes_updated_at
AFTER UPDATE ON codes
BEGIN
    UPDATE codes SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
