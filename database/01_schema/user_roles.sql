-- user_roles.sql
CREATE TABLE user_role (
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES "user"(user_id),
    FOREIGN KEY (role_id) REFERENCES role(role_id)
);