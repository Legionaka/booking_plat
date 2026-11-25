# Security overview

## Threat summary

The application protects customer identity, booking data, payment state, and tenant-owned records. Main threats include credential guessing, CSRF, cross-tenant access, forged payment callbacks, replayed jobs/webhooks, unsafe forwarded headers, and secret disclosure through logs or deployment configuration.

## Controls

- Password hashing, server-side Redis sessions, HttpOnly/SameSite cookies, CSRF tokens, configurable rate limits, and role checks.
- Tenant-scoped service queries and database constraints; cross-business access is hidden as not found.
- PayFast signature, source, merchant, amount and server-validation checks; idempotent provider references.
- Email secrets from the environment; bounded timeout/retry classification; sensitive values and bodies omitted from logs.
- Strict Content Security Policy, route-specific PayFast form action, self-hosted assets, no inline script/style, and frontend policy scanning.
- Production guards for secure cookies, trusted proxies, external database/Redis, payment mode, sender configuration, and non-default secrets.

## Known limitations

Registration distinguishes duplicate email addresses, enabling account enumeration. Refunds are manual, including late payment after cancellation. Staff invitation, TOTP, session management UI, platform-admin console, and waitlist are deferred. Hosting and database operators remain trusted.

See root [SECURITY.md](../SECURITY.md) for private vulnerability reporting.
