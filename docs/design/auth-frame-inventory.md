# Authentication and onboarding Figma frame inventory

Source node: [F • Authentication and onboarding](https://www.figma.com/design/u1iNRYeax7OcV1qGksKGcn/Untitled?node-id=20-837). This table covers all 181 direct frame children of node `20:837`; responsive variants are separate frames. The frame name gives its semantic screen/state (for example, “Verify email cooldown”); the viewport column gives the breakpoint dimensions. “Outside F1” rows are mapped for planning and were not implemented in this slice.

| Node | Frame name | Size | Viewport | Route | Template | Scope |
|---|---|---:|---|---|---|---|
| 20:848 | Auth • Shared components | 1440 × 1919 | Shared components | /dev/components | `dev/components.html` | F1 shared states |
| 20:915 | Customer sign in • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:922 | Customer register • 1440 | 1440 × 1120 | 1440 | /auth/register | `auth/register.html` | F1 |
| 20:929 | Business sign in • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:936 | Admin sign in • 1440 | 1440 × 1120 | 1440 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:941 | Forgot password • 1440 | 1440 × 1120 | 1440 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:948 | Check your email • 1440 | 1440 × 1120 | 1440 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:955 | Set new password • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 |
| 20:962 | Password updated • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:969 | Verify email waiting • 1440 | 1440 × 1120 | 1440 | /auth/verify | `auth/verify.html` | F1 |
| 20:976 | Verify email cooldown • 1440 | 1440 × 1120 | 1440 | /auth/verify | `auth/verify.html` | F1 |
| 20:983 | Verify email success • 1440 | 1440 × 1120 | 1440 | /auth/verify | `auth/verify.html` | F1 |
| 20:990 | Accept staff invite • 1440 | 1440 × 1120 | 1440 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:997 | Invite accepted • 1440 | 1440 × 1120 | 1440 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:1004 | Two-step verification • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:1011 | Backup code • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:1018 | Create business • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:1025 | Add first service • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:1032 | Set working hours • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:1039 | Add staff • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:1046 | Share booking link • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:1053 | Account security • 1440 | 1440 × 1120 | 1440 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:1060 | Business access denied • 1440 | 1440 × 1120 | 1440 | /app/access-denied (deferred) | `owner/access_denied.html (not built)` | Outside F1; no dedicated page/API |
| 20:1067 | Switch business • 1440 | 1440 × 1120 | 1440 | /app/switch-business (deferred) | `owner/switch_business.html (not built)` | Outside F1; no business-switch route |
| 20:1074 | Account locked • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:1081 | Offline sign in • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:1088 | Sign in error • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:1095 | Password visible and caps lock • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:1102 | Signing in • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:2964 | Signed-in owner dashboard • 1440 | 1440 × 1504 | 1440 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:3163 | Guest booking • 390 | 390 × 1218 | 390 | /b/<slug>/book (deferred) | `customer/booking.html (not built)` | Deferred: guest checkout |
| 20:3197 | Customer bookings • 390 | 390 × 1130 | 390 | /account/bookings (outside F1) | `customer/ (not built)` | Outside F1 |
| 20:3223 | Signed-in admin health • 1440 | 1440 × 1120 | 1440 | /platform/health (outside F1) | `platform/ (not built)` | Outside F1 |
| 20:3279 | Staff calendar • 1440 | 1440 × 1120 | 1440 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:3302 | Onboarding complete dashboard • 1440 | 1440 × 1120 | 1440 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:3319 | Setup draft dashboard • 1440 | 1440 × 1120 | 1440 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:3403 | Account security enabled • 1440 | 1440 × 1120 | 1440 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:3443 | Session expired modal • 1440 | 440 × 346 | 1440 | signed-in page modal | `components/session_expired.html` | F1 component |
| 20:3557 | Password reset email • 1440 | 1440 × 1120 | 1440 | email link to /auth/reset | `app/services/email.py` (plain-text SMTP) | F1 email link; no rendered email frame/template |
| 20:3568 | Set up two-step verification • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:3610 | Customer forgot password • 1440 | 1440 × 1120 | 1440 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:3640 | Customer check your email • 1440 | 1440 × 1120 | 1440 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:3670 | Customer set new password • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 |
| 20:3706 | Customer password updated • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:3734 | Admin forgot password • 1440 | 1440 × 1120 | 1440 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:3761 | Admin check your email • 1440 | 1440 × 1120 | 1440 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:3788 | Admin set new password • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 |
| 20:3821 | Admin password updated • 1440 | 1440 × 1120 | 1440 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:3846 | Admin two-step verification • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:3873 | Admin backup code • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:3899 | Corner Cut staff calendar • 1440 | 1440 × 1120 | 1440 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:4217 | Customer account locked • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:4252 | Customer offline sign in • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:4287 | Admin account locked • 1440 | 1440 × 1120 | 1440 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:4319 | Admin offline sign in • 1440 | 1440 × 1120 | 1440 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:4351 | Customer sign in error • 1440 | 1440 × 1120 | 1440 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:4405 | Admin sign in error • 1440 | 1440 × 1120 | 1440 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:4430 | Guest booking • 1440 | 1440 × 1120 | 1440 | /b/<slug>/book (deferred) | `customer/booking.html (not built)` | Deferred: guest checkout |
| 20:4464 | Customer bookings • 1440 | 1440 × 1120 | 1440 | /account/bookings (outside F1) | `customer/ (not built)` | Outside F1 |
| 20:4581 | Customer sign in • 390 | 390 × 969 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:4651 | Customer register • 390 | 390 × 1002 | 390 | /auth/register | `auth/register.html` | F1 |
| 20:4723 | Business sign in • 390 | 390 × 919 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:4796 | Admin sign in • 390 | 390 × 844 | 390 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:4832 | Forgot password • 390 | 390 × 844 | 390 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:4888 | Check your email • 390 | 390 × 844 | 390 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:4944 | Set new password • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 |
| 20:5014 | Password updated • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:5064 | Verify email waiting • 390 | 390 × 844 | 390 | /auth/verify | `auth/verify.html` | F1 |
| 20:5116 | Verify email cooldown • 390 | 390 × 844 | 390 | /auth/verify | `auth/verify.html` | F1 |
| 20:5171 | Verify email success • 390 | 390 × 844 | 390 | /auth/verify | `auth/verify.html` | F1 |
| 20:5217 | Accept staff invite • 390 | 390 × 844 | 390 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:5280 | Invite accepted • 390 | 390 × 844 | 390 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:5330 | Two-step verification • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:5398 | Backup code • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:5453 | Create business • 390 | 390 × 887 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:5526 | Add first service • 390 | 390 × 995 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:5606 | Set working hours • 390 | 390 × 1027 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:5702 | Add staff • 390 | 390 × 985 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:5778 | Share booking link • 390 | 390 × 982 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:5851 | Account security • 390 | 390 × 921 | 390 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:5916 | Business access denied • 390 | 390 × 844 | 390 | /app/access-denied (deferred) | `owner/access_denied.html (not built)` | Outside F1; no dedicated page/API |
| 20:5969 | Switch business • 390 | 390 × 844 | 390 | /app/switch-business (deferred) | `owner/switch_business.html (not built)` | Outside F1; no business-switch route |
| 20:6028 | Account locked • 390 | 390 × 844 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6083 | Offline sign in • 390 | 390 × 844 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6138 | Sign in error • 390 | 390 × 1022 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6214 | Password visible and caps lock • 390 | 390 × 952 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6288 | Signing in • 390 | 390 × 919 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6361 | Account security enabled • 390 | 390 × 921 | 390 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:6426 | Set up two-step verification • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:6491 | Customer forgot password • 390 | 390 × 844 | 390 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:6543 | Customer check your email • 390 | 390 × 844 | 390 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:6595 | Customer set new password • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 |
| 20:6661 | Customer password updated • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:6707 | Admin forgot password • 390 | 390 × 844 | 390 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:6731 | Admin check your email • 390 | 390 × 844 | 390 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:6755 | Admin set new password • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 |
| 20:6793 | Admin password updated • 390 | 390 × 844 | 390 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:6811 | Admin two-step verification • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:6847 | Admin backup code • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:6870 | Customer account locked • 390 | 390 × 844 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6921 | Customer offline sign in • 390 | 390 × 844 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:6972 | Admin account locked • 390 | 390 × 844 | 390 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:6995 | Admin offline sign in • 390 | 390 × 844 | 390 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:7018 | Customer sign in error • 390 | 390 × 1022 | 390 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:7090 | Admin sign in error • 390 | 390 × 935 | 390 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:7129 | Customer sign in • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:7199 | Customer register • 820 | 820 × 1180 | 820 | /auth/register | `auth/register.html` | F1 |
| 20:7271 | Business sign in • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:7344 | Admin sign in • 820 | 820 × 1180 | 820 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:7380 | Forgot password • 820 | 820 × 1180 | 820 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:7436 | Check your email • 820 | 820 × 1180 | 820 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:7492 | Set new password • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 |
| 20:7562 | Password updated • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:7612 | Verify email waiting • 820 | 820 × 1180 | 820 | /auth/verify | `auth/verify.html` | F1 |
| 20:7664 | Verify email cooldown • 820 | 820 × 1180 | 820 | /auth/verify | `auth/verify.html` | F1 |
| 20:7719 | Verify email success • 820 | 820 × 1180 | 820 | /auth/verify | `auth/verify.html` | F1 |
| 20:7765 | Accept staff invite • 820 | 820 × 1180 | 820 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:7828 | Invite accepted • 820 | 820 × 1180 | 820 | /auth/invite (deferred) | `auth/invite.html (not built)` | Deferred: no invite API |
| 20:7878 | Two-step verification • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:7946 | Backup code • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:8001 | Create business • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:8074 | Add first service • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:8154 | Set working hours • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:8250 | Add staff • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:8326 | Share booking link • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:8399 | Account security • 820 | 820 × 1180 | 820 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:8464 | Business access denied • 820 | 820 × 1180 | 820 | /app/access-denied (deferred) | `owner/access_denied.html (not built)` | Outside F1; no dedicated page/API |
| 20:8517 | Switch business • 820 | 820 × 1180 | 820 | /app/switch-business (deferred) | `owner/switch_business.html (not built)` | Outside F1; no business-switch route |
| 20:8576 | Account locked • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:8631 | Offline sign in • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:8686 | Sign in error • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:8762 | Password visible and caps lock • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:8836 | Signing in • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:8909 | Account security enabled • 820 | 820 × 1180 | 820 | /auth/sessions (deferred) | `auth/security.html (not built)` | Deferred: no session list API |
| 20:8974 | Set up two-step verification • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:9039 | Customer forgot password • 820 | 820 × 1180 | 820 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:9091 | Customer check your email • 820 | 820 × 1180 | 820 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:9143 | Customer set new password • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 |
| 20:9209 | Customer password updated • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:9255 | Admin forgot password • 820 | 820 × 1180 | 820 | /auth/forgot | `auth/forgot.html` | F1 |
| 20:9279 | Admin check your email • 820 | 820 × 1180 | 820 | /auth/forgot/sent | `auth/forgot_sent.html` | F1 reset confirmation |
| 20:9303 | Admin set new password • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 |
| 20:9341 | Admin password updated • 820 | 820 × 1180 | 820 | /auth/reset | `auth/reset.html` | F1 success state |
| 20:9359 | Admin two-step verification • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:9395 | Admin backup code • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:9418 | Customer account locked • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:9469 | Customer offline sign in • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:9520 | Admin account locked • 820 | 820 × 1180 | 820 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:9543 | Admin offline sign in • 820 | 820 × 1180 | 820 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:9566 | Customer sign in error • 820 | 820 × 1180 | 820 | /auth/login | `auth/login.html` | F1; deferred unsupported variants marked below |
| 20:9638 | Admin sign in error • 820 | 820 × 1180 | 820 | /platform/login (deferred) | `platform/login.html (not built)` | Deferred: no platform-admin auth route or role |
| 20:9677 | Signed-in owner dashboard • 390 | 390 × 2664 | 390 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:9790 | Signed-in admin health • 390 | 390 × 1836 | 390 | /platform/health (outside F1) | `platform/ (not built)` | Outside F1 |
| 20:9837 | Signed-in owner dashboard • 820 | 820 × 2304 | 820 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:9951 | Signed-in admin health • 820 | 820 × 1807 | 820 | /platform/health (outside F1) | `platform/ (not built)` | Outside F1 |
| 20:9998 | Guest booking • 820 | 820 × 1180 | 820 | /b/<slug>/book (deferred) | `customer/booking.html (not built)` | Deferred: guest checkout |
| 20:10032 | Customer bookings • 820 | 820 × 1180 | 820 | /account/bookings (outside F1) | `customer/ (not built)` | Outside F1 |
| 20:10058 | Staff calendar • 390 | 390 × 974 | 390 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10081 | Corner Cut staff calendar • 390 | 390 × 974 | 390 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10104 | Onboarding complete dashboard • 390 | 390 × 1220 | 390 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:10148 | Setup draft dashboard • 390 | 390 × 1034 | 390 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10187 | Password reset email • 390 | 390 × 844 | 390 | email link to /auth/reset | `app/services/email.py` (plain-text SMTP) | F1 email link; no rendered email frame/template |
| 20:10198 | Staff calendar • 820 | 820 × 1180 | 820 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10221 | Corner Cut staff calendar • 820 | 820 × 1180 | 820 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10244 | Onboarding complete dashboard • 820 | 820 × 1180 | 820 | /app/onboarding (outside F1) | `auth/onboarding.html (not built)` | Outside F1; backend onboarding APIs exist in part |
| 20:10288 | Setup draft dashboard • 820 | 820 × 1180 | 820 | /app (outside F1) | `owner/ (not built)` | Outside F1 |
| 20:10327 | Password reset email • 820 | 820 × 1180 | 820 | email link to /auth/reset | `app/services/email.py` (plain-text SMTP) | F1 email link; no rendered email frame/template |
| 20:10338 | Session expired modal • 390 | 358 × 346 | 390 | signed-in page modal | `components/session_expired.html` | F1 component |
| 20:10347 | Session expired modal • 820 | 440 × 346 | 820 | signed-in page modal | `components/session_expired.html` | F1 component |
| 20:10390 | Two-step verification resent • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10416 | Admin two-step verification resent • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10442 | Set up two-step verification resent • 1440 | 1440 × 1120 | 1440 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10467 | Two-step verification resent • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10486 | Admin two-step verification resent • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10506 | Set up two-step verification resent • 820 | 820 × 1180 | 820 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10524 | Two-step verification resent • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10543 | Admin two-step verification resent • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:10563 | Set up two-step verification resent • 390 | 390 × 844 | 390 | /auth/2fa (deferred) | `auth/2fa.html (not built)` | Deferred: no two-step API |
| 20:11364 | Session expiry preview • 1440 | 1440 × 1504 | 1440 | /app (outside F1) | `auth/placeholder.html` + `components/session_expired.html` | Owner preview; dashboard deferred |
| 20:11467 | Session expiry preview • 820 | 820 × 2304 | 820 | /app (outside F1) | `auth/placeholder.html` + `components/session_expired.html` | Owner preview; dashboard deferred |
| 20:11553 | Session expiry preview • 390 | 390 × 2664 | 390 | /app (outside F1) | `auth/placeholder.html` + `components/session_expired.html` | Owner preview; dashboard deferred |

## Deferred authentication states

Guest checkout, Google/social sign-in, staff invite acceptance, two-step verification/backup codes, and session listing remain deferred because this backend has no matching supported route/API. Platform administrator sign-in is also deferred: Figma contains an admin frame, but no platform-admin auth route or role exists. Lockout is not currently a distinct backend response; UI retains standard auth error handling. Authentication token requests and sign-in state variants are implemented on their shared routes rather than as separate routes.

