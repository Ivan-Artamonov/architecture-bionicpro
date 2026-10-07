-- Synthetic telemetry, deliberately one day old so the scheduled DAG can process it.
INSERT INTO bionicpro.telemetry VALUES
(101, now64(3) - INTERVAL 1 DAY, 1, 0.71),
(101, now64(3) - INTERVAL 1 DAY, 0, 0.66),
(102, now64(3) - INTERVAL 1 DAY, 1, 0.81);
