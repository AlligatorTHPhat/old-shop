-- system_feedback.sql
CREATE TABLE system_feedback (
    feedback_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES "user"(user_id) ON DELETE SET NULL,
    guest_email VARCHAR(255),
    subject VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    status SMALLINT DEFAULT 0, -- 0: Pending, 1: Reviewed, 2: Resolved
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_system_feedback_user ON system_feedback(user_id);
CREATE INDEX idx_system_feedback_status ON system_feedback(status);
CREATE INDEX idx_system_feedback_created_at ON system_feedback(created_at);
