-- PostgreSQL schema from docs/planning.md.
-- Apply schema changes through Alembic migrations; this file is the design reference.

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE businesses (
  id                  BIGSERIAL PRIMARY KEY,
  slug                CITEXT UNIQUE NOT NULL,
  name                TEXT NOT NULL,
  timezone            TEXT NOT NULL DEFAULT 'Africa/Johannesburg',
  cancel_cutoff_hours INT NOT NULL DEFAULT 24,
  slot_step_min       INT NOT NULL DEFAULT 15,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  email         CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name     TEXT NOT NULL,
  phone         TEXT,
  verified_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('owner', 'staff')),
  PRIMARY KEY (user_id, business_id)
);

CREATE TABLE staff (
  id           BIGSERIAL PRIMARY KEY,
  business_id  BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  user_id      BIGINT REFERENCES users(id),
  display_name TEXT NOT NULL,
  active       BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE services (
  id            BIGSERIAL PRIMARY KEY,
  business_id   BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  duration_min  INT NOT NULL CHECK (duration_min > 0),
  buffer_min    INT NOT NULL DEFAULT 0 CHECK (buffer_min >= 0),
  price_cents   INT NOT NULL CHECK (price_cents >= 0),
  deposit_cents INT NOT NULL DEFAULT 0 CHECK (deposit_cents >= 0),
  active        BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE staff_services (
  staff_id   BIGINT REFERENCES staff(id) ON DELETE CASCADE,
  service_id BIGINT REFERENCES services(id) ON DELETE CASCADE,
  PRIMARY KEY (staff_id, service_id)
);

CREATE TABLE working_hours (
  id         BIGSERIAL PRIMARY KEY,
  staff_id   BIGINT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  weekday    SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time   TIME NOT NULL,
  CHECK (end_time > start_time)
);

CREATE TABLE time_off (
  id       BIGSERIAL PRIMARY KEY,
  staff_id BIGINT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  during   TSTZRANGE NOT NULL,
  reason   TEXT
);

CREATE TABLE bookings (
  id              BIGSERIAL PRIMARY KEY,
  business_id     BIGINT NOT NULL REFERENCES businesses(id),
  customer_id     BIGINT NOT NULL REFERENCES users(id),
  staff_id        BIGINT NOT NULL REFERENCES staff(id),
  service_id      BIGINT NOT NULL REFERENCES services(id),
  start_at        TIMESTAMPTZ NOT NULL,
  end_at          TIMESTAMPTZ NOT NULL,
  blocked_until   TIMESTAMPTZ NOT NULL, -- end_at plus service buffer
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed', 'no_show')),
  hold_expires_at TIMESTAMPTZ, -- pending holds expire
  price_cents     INT NOT NULL, -- price snapshot at booking time
  deposit_cents   INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_at > start_at AND blocked_until >= end_at),
  EXCLUDE USING gist (
    staff_id WITH =,
    tstzrange(start_at, blocked_until, '[)') WITH &&
  ) WHERE (status IN ('pending', 'confirmed'))
);

CREATE INDEX bookings_business_start ON bookings (business_id, start_at);
CREATE INDEX bookings_customer ON bookings (customer_id);

CREATE TABLE payments (
  id           BIGSERIAL PRIMARY KEY,
  booking_id   BIGINT NOT NULL REFERENCES bookings(id),
  provider     TEXT NOT NULL,
  provider_ref TEXT NOT NULL,
  amount_cents INT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
  raw_payload  JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_ref) -- webhook idempotency
);

CREATE TABLE notifications (
  id            BIGSERIAL PRIMARY KEY,
  booking_id    BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL, -- confirmation, reminder_24h, reminder_2h, waitlist
  scheduled_for TIMESTAMPTZ NOT NULL,
  sent_at       TIMESTAMPTZ,
  status        TEXT NOT NULL DEFAULT 'queued',
  UNIQUE (booking_id, kind)
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  business_id BIGINT REFERENCES businesses(id),
  actor_id    BIGINT REFERENCES users(id),
  entity      TEXT NOT NULL,
  entity_id   BIGINT NOT NULL,
  action      TEXT NOT NULL,
  diff        JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
