# ADR 0010: Use a strict Content Security Policy

- Status: Accepted
- Decision: Avoid inline scripts and styles, self-host frontend assets, and add only the route-specific PayFast form action needed for checkout.
- Reason: Restrict script injection and keep external dependencies out of product pages.
- Consequences: JavaScript and styling live in external files; frontend policy scans guard the rule.
