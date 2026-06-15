CREATE EXTENSION IF NOT EXISTS pg_cron;

INSERT INTO time_window_sizes (size, time_delta)
VALUES
    ('xs', INTERVAL '1 minute'),
    ('s', INTERVAL '5 minutes'),
    ('m', INTERVAL '30 minutes'),
    ('l', INTERVAL '3 hours'),
    ('xl', INTERVAL '1 day'),
    ('xxl', INTERVAL '1 month')
ON CONFLICT (size)
DO UPDATE SET time_delta = EXCLUDED.time_delta;

CREATE OR REPLACE FUNCTION fill_log_summaries(summary_size TEXT)
RETURNS void
LANGUAGE sql
AS $$
    WITH bounds AS (
        SELECT
            summary_size AS time_window,
            date_trunc('minute', NOW()) - time_delta AS start_time,
            date_trunc('minute', NOW()) AS end_time
        FROM time_window_sizes
        WHERE size = summary_size
    ),
    summary_counts AS (
        SELECT
            r.org_id,
            b.time_window,
            b.start_time,
            COUNT(*)::INT AS log_count
        FROM bounds b
        JOIN raw_logs r
          ON r.timestamp >= b.start_time
         AND r.timestamp < b.end_time
        GROUP BY r.org_id, b.time_window, b.start_time
    ),
    inserted_summaries AS (
        INSERT INTO log_summaries (org_id, time_window, start_time, log_count)
        SELECT org_id, time_window, start_time, log_count
        FROM summary_counts
        ON CONFLICT (org_id, time_window, start_time) DO NOTHING
        RETURNING id, org_id, time_window, start_time
    ),
    target_summaries AS (
        SELECT id, org_id, time_window, start_time
        FROM inserted_summaries

        UNION

        SELECT ls.id, ls.org_id, ls.time_window, ls.start_time
        FROM log_summaries ls
        JOIN summary_counts sc
          ON sc.org_id = ls.org_id
         AND sc.time_window = ls.time_window
         AND sc.start_time = ls.start_time
    ),
    signature_counts AS (
        SELECT
            ts.id AS summary_id,
            r.signature_id AS log_signature_id,
            s.log_level,
            COUNT(*)::INT AS log_count
        FROM bounds b
        JOIN target_summaries ts
          ON ts.time_window = b.time_window
         AND ts.start_time = b.start_time
        JOIN raw_logs r
          ON r.org_id = ts.org_id
         AND r.timestamp >= b.start_time
         AND r.timestamp < b.end_time
        JOIN log_signatures s
          ON s.id = r.signature_id
         AND s.org_id = r.org_id
        GROUP BY ts.id, r.signature_id, s.log_level
    )
    INSERT INTO log_summary_signatures (
        summary_id,
        log_signature_id,
        log_level,
        log_count
    )
    SELECT
        summary_id,
        log_signature_id,
        log_level,
        log_count
    FROM signature_counts
    ON CONFLICT (summary_id, log_signature_id) DO NOTHING;
$$;

DO $$
DECLARE
    summary_job RECORD;
BEGIN
    FOR summary_job IN
        SELECT *
        FROM (
            VALUES
                ('fill_log_summaries_xs', '* * * * *', 'SELECT fill_log_summaries(''xs'');'),
                ('fill_log_summaries_s', '*/5 * * * *', 'SELECT fill_log_summaries(''s'');'),
                ('fill_log_summaries_m', '*/30 * * * *', 'SELECT fill_log_summaries(''m'');'),
                ('fill_log_summaries_l', '0 */3 * * *', 'SELECT fill_log_summaries(''l'');'),
                ('fill_log_summaries_xl', '0 0 * * *', 'SELECT fill_log_summaries(''xl'');'),
                ('fill_log_summaries_xxl', '0 0 1 * *', 'SELECT fill_log_summaries(''xxl'');')
        ) AS jobs(jobname, schedule, command)
    LOOP
        UPDATE cron.job
        SET schedule = summary_job.schedule,
            command = summary_job.command
        WHERE jobname = summary_job.jobname;

        IF NOT FOUND THEN
            PERFORM cron.schedule(
                summary_job.jobname,
                summary_job.schedule,
                summary_job.command
            );
        END IF;
    END LOOP;
END;
$$;
