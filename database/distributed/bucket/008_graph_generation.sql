CREATE TABLE graph_projection_state(
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),generation integer NOT NULL DEFAULT 1 CHECK(generation>0),
 state text NOT NULL DEFAULT 'active' CHECK(state IN ('active','rebuilding'))
);
INSERT INTO graph_projection_state DEFAULT VALUES;
