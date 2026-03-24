-- Seed data: anonymous user used when auth is not yet configured
INSERT INTO users (id, display_name)
VALUES ('00000000-0000-0000-0000-000000000001', 'Anonymous')
ON CONFLICT (id) DO NOTHING;
