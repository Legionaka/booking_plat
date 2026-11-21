# ADR 0002: HTTPS email API for Render Free

- Status: accepted
- Date: 2026-11-21

## Context

Render Free web services block outbound SMTP on ports 25, 465, and 587. Email verification, password resets, booking confirmations, and reminders need a transport available from the free web and worker services.

## Decision

Keep the console and SMTP backends, and add a standard-library HTTPS API backend selected by `EMAIL_BACKEND=http_api`. Choose Brevo, Resend, or Mailgun through `EMAIL_PROVIDER`; hold keys and sender settings in environment variables. Use verified TLS, a 10 second timeout, CR/LF-stripped header values, masked recipient logging, and no logging of keys or message bodies. Retry timeouts, network failures, 429, and 5xx responses; mark other 4xx failures permanent in the outbox.

## Consequences

Render Free uses HTTPS APIs on port 443. Local development and Mailpit continue to use SMTP. Provider selection can change through environment configuration without application dependencies or schema changes. Provider-specific quotas and sender-verification rules must be checked in the provider dashboard.
