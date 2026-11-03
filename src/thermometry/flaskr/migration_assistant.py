# -*- coding: utf-8 -*-
"""
Script to move an existing database onto faster storage settings. Only policies and indexes
change, never readings. It is safe to re-run and to run while the website is up.

1) Compress measurement chunks once they are a week old instead of two months. Almost every
   query reads the last week, which stays uncompressed, while older data shrinks ~18x and can
   still be queried as before. Chunks that are already old enough are compressed straight away
   rather than waiting for the policy's next run.
2) Drop idx_measurement_sensor_time. It is a non-unique copy of the (sensor_id, time) primary
   key, so every insert was maintaining a second identical index.

Run on the server (database settings come from config.py):
    uv run python -m thermometry.flaskr.migration_assistant --dry-run   # report what would change
    uv run python -m thermometry.flaskr.migration_assistant
"""

import argparse
import time

import psycopg2
import psycopg2.errors

from thermometry import config

COMPRESS_AFTER = "10 days"
DUPLICATE_INDEX = "idx_measurement_sensor_time"


def report(cur):
    """Print the state of the measurement hypertable"""
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
    print(f"  TimescaleDB {cur.fetchone()[0]}")

    cur.execute("SELECT pg_size_pretty(total_bytes) FROM hypertable_detailed_size('measurement')")
    size = cur.fetchone()[0]
    cur.execute("""
    SELECT count(*) FILTER (WHERE is_compressed), count(*) FILTER (WHERE NOT is_compressed)
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'measurement'
    """)
    compressed, uncompressed = cur.fetchone()
    print(f"  measurement: {size} with {compressed} compressed and {uncompressed} uncompressed chunks")

    # The run history shows whether the compression job has actually been working
    cur.execute("""
    SELECT j.config->>'compress_after', s.last_run_status,
           to_char(s.last_successful_finish, 'YYYY-MM-DD HH24:MI'), s.total_failures
    FROM timescaledb_information.jobs j
    LEFT JOIN timescaledb_information.job_stats s ON s.job_id = j.job_id
    WHERE j.hypertable_name = 'measurement' AND j.proc_name = 'policy_compression'
    """)
    policy = cur.fetchone()
    if policy is None:
        print("  compression policy: none")
    else:
        after, status, last_success, failures = policy
        print(f"  compression policy: after {after}. Last run: {status or 'never'}, "
              f"last success: {last_success or 'never'}, failures: {failures or 0}")

    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'measurement' ORDER BY indexname")
    print(f"  indexes: {', '.join(row[0] for row in cur.fetchall())}")


def drop_duplicate_index(conn, cur, dry_run: bool):
    """Drop the non-unique copy of the primary key from the hypertable and all its chunks"""
    cur.execute("SELECT to_regclass(%s)", (DUPLICATE_INDEX,))
    if cur.fetchone()[0] is None:
        print(f"{DUPLICATE_INDEX}: already dropped")
        return

    # Only drop it where each chunk really holds its own copy, separate from the primary key's index
    cur.execute("""
    SELECT count(*), pg_size_pretty(coalesce(sum(pg_relation_size(i.indexrelid)), 0))
    FROM timescaledb_information.chunks ch
    JOIN pg_namespace n ON n.nspname = ch.chunk_schema
    JOIN pg_class t ON t.relname = ch.chunk_name AND t.relnamespace = n.oid
    JOIN pg_index i ON i.indrelid = t.oid
    WHERE ch.hypertable_name = 'measurement'
      AND NOT i.indisunique
      AND pg_get_indexdef(i.indexrelid) LIKE '%USING btree (sensor_id, "time")'
    """)
    copies, size = cur.fetchone()
    conn.commit()
    if copies == 0:
        print(f"{DUPLICATE_INDEX}: not built separately on any chunk, so leaving it alone")
        return

    print(f"{DUPLICATE_INDEX}: dropping it from {copies} chunks frees {size}")
    if dry_run:
        return
    try:
        cur.execute(f"DROP INDEX {DUPLICATE_INDEX}")
        conn.commit()
    except psycopg2.errors.LockNotAvailable:
        conn.rollback()
        print(f"  The table was too busy to drop {DUPLICATE_INDEX}. Run this script again later")
        return
    print("  dropped")


def policy_is_current(conn, cur) -> bool:
    """Return whether the compression policy already compresses after COMPRESS_AFTER"""
    cur.execute("""
    SELECT (config->>'compress_after')::interval = %s::interval
    FROM timescaledb_information.jobs
    WHERE hypertable_name = 'measurement' AND proc_name = 'policy_compression'
    """, (COMPRESS_AFTER,))
    row = cur.fetchone()
    conn.commit()
    return row is not None and row[0]


def set_compression_policy(conn, cur, dry_run: bool):
    """Replace the compression policy so that chunks are compressed after COMPRESS_AFTER"""
    print(f"Compression policy: compress chunks once they are {COMPRESS_AFTER} old")
    if dry_run:
        return
    # Swap the policy in one transaction so that the table is never left without one
    cur.execute("SELECT remove_compression_policy('measurement', if_exists => true)")
    cur.execute("SELECT add_compression_policy('measurement', compress_after => %s::interval)", (COMPRESS_AFTER,))
    conn.commit()
    print("  updated")


def compress_old_chunks(conn, cur, dry_run: bool):
    """Compress every chunk the new policy will cover now, instead of leaving the backlog to it"""
    cur.execute("""
    SELECT format('%%I.%%I', chunk_schema, chunk_name), range_start, range_end
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'measurement' AND NOT is_compressed AND range_end < now() - %s::interval
    ORDER BY range_start
    """, (COMPRESS_AFTER,))
    chunks = cur.fetchall()
    conn.commit()

    print(f"Uncompressed chunks older than {COMPRESS_AFTER}: {len(chunks)}")
    if dry_run or not chunks:
        return
    print("  Compressing them now. Safe to interrupt: run this script again to carry on")
    for chunk, start, end in chunks:
        t0 = time.time()
        try:
            cur.execute("SELECT compress_chunk(%s::regclass, if_not_compressed => true)", (chunk,))
            conn.commit()  # One chunk per transaction so each one's locks are released straight away
        except psycopg2.errors.DuplicateObject:
            conn.rollback()  # The old policy's job compressed it while we were waiting for it
            print(f"  {start:%Y-%m-%d} to {end:%Y-%m-%d}: already compressed")
            continue
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            print(f"  {start:%Y-%m-%d} to {end:%Y-%m-%d}: busy, skipped. The new policy will compress it")
            continue
        print(f"  {start:%Y-%m-%d} to {end:%Y-%m-%d}: compressed in {time.time() - t0:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Move the thermometry database onto faster storage settings")
    parser.add_argument("--dry-run", action="store_true", help="only report what would change")
    args = parser.parse_args()

    conn = psycopg2.connect(**config.DATABASE)
    cur = conn.cursor()
    # Give up instead of waiting for a lock. Queries from the website would queue behind ours meanwhile
    cur.execute("SET lock_timeout = '5s'")
    conn.commit()

    print("Before:")
    report(cur)
    conn.commit()
    print()

    drop_duplicate_index(conn, cur, args.dry_run)
    if policy_is_current(conn, cur):
        print(f"Compression policy: already compresses after {COMPRESS_AFTER}")
    else:
        # Clear the backlog before switching. The new policy's job starts as soon as it is added, and
        # compressing a chunk from two sessions at once makes the job fail. The old policy only works
        # on chunks over two months old, which it has normally compressed already
        compress_old_chunks(conn, cur, args.dry_run)
        set_compression_policy(conn, cur, args.dry_run)

    if not args.dry_run:
        print("\nAfter:")
        report(cur)
        conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
