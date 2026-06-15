CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE OR REPLACE FUNCTION cleanup_daily_ttl()
RETURNS void
LANGUAGE sql
AS $$
    DELETE FROM log_summaries
    WHERE time_window IN ('xs', 's')
      AND start_time < NOW() - INTERVAL '1 day';

    DELETE FROM raw_logs
    WHERE timestamp < NOW() - INTERVAL '7 days';
$$;

CREATE OR REPLACE FUNCTION cleanup_monthly_ttl()
RETURNS void
LANGUAGE sql
AS $$
    DELETE FROM log_summaries
    WHERE time_window IN ('m', 'l', 'xl')
      AND start_time < NOW() - INTERVAL '1 month';

    DELETE FROM alerts
    WHERE closed_at IS NOT NULL
      AND closed_at < NOW() - INTERVAL '90 days';

    DELETE FROM api_keys
    WHERE revoked_at IS NOT NULL
      AND revoked_at < NOW() - INTERVAL '90 days';
$$;

DO $$
DECLARE
    ttl_job RECORD;
BEGIN
    FOR ttl_job IN
        SELECT *
        FROM (
            VALUES
                ('cleanup_daily_ttl', '15 0 * * *', 'SELECT cleanup_daily_ttl();'),
                ('cleanup_monthly_ttl', '30 0 1 * *', 'SELECT cleanup_monthly_ttl();')
        ) AS jobs(jobname, schedule, command)
    LOOP
        UPDATE cron.job
        SET schedule = ttl_job.schedule,
            command = ttl_job.command
        WHERE jobname = ttl_job.jobname;

        IF NOT FOUND THEN
            PERFORM cron.schedule(
                ttl_job.jobname,
                ttl_job.schedule,
                ttl_job.command
            );
        END IF;
    END LOOP;
END;
$$;
