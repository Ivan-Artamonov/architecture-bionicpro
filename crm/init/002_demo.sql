-- Synthetic demo records, linked to stable Keycloak subjects.
INSERT INTO customers(id,keycloak_subject,display_name) VALUES
(1,'159b5d92-9a16-51bc-a24d-bd3cc84a8ad6','Demo User One'),
(2,'3cd2a0d4-423f-5bf9-a305-834b7ae8af61','Demo User Two')
ON CONFLICT DO NOTHING;
INSERT INTO prostheses(id,customer_id,serial_number) VALUES
(101,1,'DEMO-101'), (102,2,'DEMO-102') ON CONFLICT DO NOTHING;
