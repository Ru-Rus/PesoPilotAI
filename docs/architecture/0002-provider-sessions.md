# ADR 0002: OIDC plus opaque sessions

Accepted. Delegate credentials to Keycloak through Authlib; validate OIDC claims and PKCE/state/nonce. Browser receives Secure HttpOnly random-cookie sessions, with only hashes stored server-side. CSRF and owner authorization remain server responsibilities. This reduces local password handling; provider production MFA/recovery/availability and revocation policy still require operational configuration.
