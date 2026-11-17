-- Postgres hardening for a real calendar. SQLite cannot express this.
-- The application also rejects overlaps in a transaction.

CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE bookings
  ADD CONSTRAINT bookings_no_overlap
  EXCLUDE USING gist (
    tstzrange(starts_at::timestamptz, ends_at::timestamptz, '[)') WITH &&
  )
  WHERE (status = 'confirmed');
