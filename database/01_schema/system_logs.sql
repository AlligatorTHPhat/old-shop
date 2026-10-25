-- system_logs.sql
CREATE TABLE system_log (
    log_id BIGSERIAL PRIMARY KEY,
    user_id INT,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id INT,
    details TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(user_id)
);

-- Indexes for performance
CREATE INDEX idx_system_log_user ON system_log(user_id);
CREATE INDEX idx_system_log_action ON system_log(action);
CREATE INDEX idx_system_log_created_at ON system_log(created_at);
