# Architecture

## Components

```mermaid
flowchart LR
  Client[Browser: customer / owner / staff] -->|HTML, JSON, session cookie| Web[Flask app and blueprints]
  Web --> Services[app/services]
  Services --> DB[(PostgreSQL)]
  Web --> Redis[(Redis: sessions, limiter, RQ)]
  Services -->|booking/payment transaction| Outbox[(Notification outbox)]
  Scheduler[Scheduler process] --> DB
  Scheduler --> Redis
  Redis --> Worker[RQ worker]
  Worker --> DB
  Worker --> Email[Console / SMTP / HTTPS API]
  Web --> Checkout[PayFast checkout]
  Checkout -->|ITN| Web
```

## Request flow

The Flask factory loads configuration, extensions, blueprints, CSP/security headers, and error handling. Blueprints parse and validate inputs, apply authentication and role checks, call services, and serialize responses. Services own transaction boundaries and tenant scoping. SQLAlchemy writes to PostgreSQL; Redis backs sessions, rate limits, and RQ. HTML pages are Jinja templates with external assets; browser requests use the JSON API.

## Booking sequence

```mermaid
sequenceDiagram
  actor Customer
  participant UI as Customer UI
  participant API as Flask API
  participant Availability as Availability service
  participant DB as PostgreSQL
  Customer->>UI: Select service, staff, date, slot
  UI->>API: GET availability
  API->>Availability: Compute local windows and occupancy
  Availability->>DB: Read schedules, time off, active bookings
  DB-->>UI: Open slots in business timezone
  UI->>API: POST booking with CSRF
  API->>Availability: Revalidate slot
  API->>DB: Insert booking and outbox rows in transaction
  DB-->>API: Commit or exclusion conflict
  API-->>UI: confirmed/pending or 409 slot_taken
```

## Payment sequence

```mermaid
sequenceDiagram
  actor Customer
  participant API as Flask API
  participant DB as PostgreSQL
  participant PF as PayFast
  Customer->>API: Request checkout for owned pending booking
  API->>DB: Create/reuse payment and signed fields
  API-->>Customer: Route-specific CSP checkout handoff
  Customer->>PF: Submit hosted payment form
  PF->>API: Form-encoded ITN callback
  API->>PF: Validate callback with provider
  API->>DB: Verify signature, amount, merchant, reference; idempotent update
  PF-->>Customer: Browser return
  Customer->>API: Poll booking status
  Note over API,DB: Browser return never confirms payment
```

## Job flow

```mermaid
sequenceDiagram
  participant Scheduler
  participant DB as PostgreSQL outbox
  participant Redis
  participant Worker as RQ worker
  participant Mail as Email backend
  Scheduler->>DB: Claim due notifications and recover stale work
  Scheduler->>Redis: Enqueue idempotent job
  Redis->>Worker: Deliver job
  Worker->>DB: Claim row and load safe template data
  Worker->>Mail: Send with bounded retry classification
  Worker->>DB: Mark sent, retryable, or permanently failed
```

## Data model

```mermaid
erDiagram
  USER ||--o{ MEMBERSHIP : has
  BUSINESS ||--o{ MEMBERSHIP : contains
  BUSINESS ||--o{ STAFF : employs
  BUSINESS ||--o{ SERVICE : offers
  STAFF }o--o{ SERVICE : assigned
  STAFF ||--o{ WORKING_HOURS : scheduled
  STAFF ||--o{ TIME_OFF : unavailable
  USER ||--o{ BOOKING : customer
  BUSINESS ||--o{ BOOKING : owns
  STAFF ||--o{ BOOKING : serves
  SERVICE ||--o{ BOOKING : booked
  BOOKING ||--o{ PAYMENT : paid_by
  BOOKING ||--o{ NOTIFICATION : triggers
  BUSINESS ||--o{ AUDIT_LOG : records
```

Alembic migrations are authoritative; `docs/schema.sql` is a reference. The booking exclusion constraint covers `staff_id` and `[start_at, blocked_until)` for pending and confirmed rows.
