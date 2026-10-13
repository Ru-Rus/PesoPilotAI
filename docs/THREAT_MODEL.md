# Threat model

Assets: financial history, session/CSRF secrets, provider configuration, identities and backups. Boundaries: browser?Next.js, proxy?API, API?provider, API?SQL Server, CI?repository/artifacts. Descriptions and CSV text are data, never instructions.

| Threat                             | Implemented mitigation                                                                 | Remaining verification/risk                                               |
| ---------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Cross-user read/write              | Server owner scope, composite account-owner FKs, two-user tests                        | New resources must inherit these controls                                 |
| Cookie replay / login forgery      | Hashes, expiry, rotation, revoke, PKCE/state/nonce/signature checks                    | Provider recovery/MFA/back-channel logout pending                         |
| CSRF / injected scripts            | Exact Origin + token, React encoding, nonce CSP, frame denial                          | Browser/a11y audit; inline styles allowed                                 |
| Financial race / double import     | Versions, atomic batch unique key, archive locks                                       | Wider load/deadlock/retry measurements pending                            |
| Upload exhaustion                  | 2 MB request body bound before parsing; 1 MB/5k CSV cap; rate limits                   | Ingress connection/time limits and concurrent memory measurements pending |
| SQL injection                      | ORM parameterized queries, no generated SQL                                            | Runtime least privilege requires external configuration                   |
| Error/log disclosure               | Sanitized API errors, request-ID-only diagnostics, disabled access logs in run command | Proxy/monitoring configuration not verified                               |
| Vulnerable dependencies            | Patched packages, pip-audit/npm audit and Bandit gates                                 | Advisory databases are point-in-time; CI execution pending                |
| Spreadsheet injection              | No export endpoint; imported text is never executed                                    | Escape dangerous prefixes when export is implemented                      |
| AI exfiltration / prompt injection | No model integration or AI SQL/tool execution                                          | Future read-only scoped tools, opt-in and adversarial eval required       |
| Backup exposure / loss             | Documented plan only                                                                   | Encryption, retention and actual restore are release blockers             |

No red-team penetration test or compliance certification is claimed. Risks are reviewed per changed scope; infrastructure policies cannot be verified from repository code alone.
