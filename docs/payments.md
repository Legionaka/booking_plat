# PayFast deposits

## Payment flow

1. A verified customer starts payment for their own pending booking. The service checks the deposit and active hold, creates or reuses a pending PayFast payment, and extends the hold to at least the PAYMENT_HOLD_MINUTES setting.
2. `POST /api/bookings/{id}/pay` returns PayFast's sandbox or live checkout action URL plus signed form fields. The authenticated browser then posts to `POST /payments/handoff/{id}`; that page renders the same server-generated fields into a form and submits it with `/static/js/payfast-handoff.js`. Only the handoff page has a CSP `form-action` exception for PayFast.
3. The customer pays on PayFast. The return URL is only a browser return; it does not confirm payment. A client can poll GET /api/me/bookings/{id} for payment_status.
4. PayFast posts an ITN to /api/payments/payfast/itn. Only a validated COMPLETE ITN can mark a payment paid and confirm its still-pending booking. Confirmation creates the slice 6 outbox rows in the same transaction.
5. FAILED and CANCELLED ITNs leave the booking pending until its hold expires. An unknown payment status is recorded on the payment without changing its status.

## ITN check order

The webhook performs checks in this order and stops at the first failure:

1. Parse the raw form body in its original order and verify the lower-case MD5 signature with constant-time comparison. Duplicate fields or a misplaced signature are rejected.
2. Resolve the PayFast source hostnames at request time and compare their current addresses with the request source IP. The resolver can be replaced in tests.
3. Compare merchant_id to the configured merchant.
4. Lock the payment identified by m_payment_id.
5. Convert amount_gross to integer cents using Decimal and compare it exactly with the stored amount.
6. POST the signed ITN parameters to PayFast's sandbox/live /eng/query/validate endpoint. A response other than VALID is rejected; a network failure returns 503 so PayFast can retry.
7. Apply the status idempotently. A late successful payment for an already-cancelled booking is recorded as paid but does not reinstate the booking.

The signature implementation follows PayFast's [Custom Payment Integration](https://developers.payfast.co.za/docs) and [ITN](https://developers.payfast.co.za/docs/itn-instant-transaction-notification/) documentation. Custom payment signatures use the form field order documented by PayFast, nonblank fields only, trimmed values URL-encoded with spaces as +, and the passphrase appended at the end. ITN verification preserves the posted field order and signs the fields before signature.

The handoff form actions are `https://www.payfast.co.za/eng/process` (live) and `https://sandbox.payfast.co.za/eng/process` (sandbox), as listed in PayFast's official [Custom Payment Integration documentation](https://developers.payfast.co.za/docs). The route-specific CSP permits form submissions only to those two hosts and this application's own origin; every other route keeps `form-action 'self'`.

## Local sandbox testing

1. Create a PayFast Sandbox account and configure PAYFAST_MERCHANT_ID, PAYFAST_MERCHANT_KEY, and PAYFAST_PASSPHRASE with sandbox credentials.
2. Set PAYFAST_SANDBOX=true.
3. Run the web app and expose its local port using a public HTTPS tunnel such as Cloudflare Tunnel or ngrok.
4. Set PUBLIC_BASE_URL to the tunnel's public HTTPS origin and restart the app. PayFast must be able to reach the generated notify_url; localhost is not publicly reachable.
5. Create a deposit booking, call its /pay endpoint, and submit the returned fields to the returned PayFast action URL. Inspect Sandbox ITN delivery and the booking's payment status.

Never log the passphrase, signatures, or full ITN payload. The local test suite injects the DNS resolver and validation HTTP call, so tests make no external network requests.

Stored ITN payloads contain customer personal data returned by PayFast (such as name and email). Limit access to payment records and set a retention period appropriate to your accounting and privacy obligations; a practical starting policy is to purge or irreversibly redact raw payloads after 13 months, retaining only the payment reference, amount, status, and timestamps needed for accounting.

## Late payment after cancellation

If COMPLETE arrives after an expired hold has already been cleaned up and the booking is cancelled, the ITN is still recorded as paid. The booking stays cancelled, the audit log records `payment_received_for_cancelled_booking`, and the transactional outbox queues a `payment_for_cancelled_booking` notification for the business owner. It says a manual refund is needed; automatic refunds are not implemented.

An owner can list paid payments with GET /api/admin/businesses/{business_id}/payments?status=paid, then compare those booking IDs with cancelled bookings from GET /api/admin/businesses/{business_id}/bookings?status=cancelled. Refund the late payment in the PayFast dashboard and record the follow-up through the business's operational process.

## Delivery guarantee

Email notification delivery is at-least-once. A crash after provider acceptance but before the sent-state database commit can cause another attempt and a duplicate email. When a real provider is configured, send a stable provider idempotency key such as notification-<id>.
