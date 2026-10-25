-- violation_logs.sql
CREATE TABLE violation_log (
    log_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    reason VARCHAR(500) NOT NULL,
    action_taken VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(user_id)
);

-- Indexes for performance
CREATE INDEX idx_violation_log_user ON violation_log(user_id);
CREATE INDEX idx_violation_log_created_at ON violation_log(created_at);
