# API contracts

Local OpenAPI: `http://127.0.0.1:8000/docs`. All finance/session-management routes require a valid session. Writes additionally require exact configured Origin and `X-CSRF-Token` from `/api/v1/auth/me`. Cookies must remain HttpOnly; do not copy real cookies into documentation.

| Endpoint                                    | Contract                                                                   |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| GET /health/live, /health/ready             | Minimal status; readiness checks DB                                        |
| GET /api/v1/auth/login, /callback           | OIDC flow; public and rate limited                                         |
| GET /api/v1/auth/me                         | Identity and in-memory CSRF token                                          |
| POST /api/v1/auth/logout                    | Revoke locally; optional provider redirect                                 |
| GET /api/v1/auth/sessions                   | Own active sessions; IDs cannot authenticate                               |
| DELETE /api/v1/auth/sessions/{id}           | Revoke own session; foreign/unknown returns 404                            |
| GET, POST /api/v1/accounts                  | List with SQL balances / create                                            |
| PATCH /api/v1/accounts/{id}                 | Complete editable state plus current version                               |
| GET, POST /api/v1/transactions              | Array list / create; limit 1?500; optional owner-checked account filter    |
| PATCH /api/v1/transactions/{id}             | Creation fields plus current version                                       |
| DELETE /api/v1/transactions/{id}?version=2  | Required current version; missing 428, stale 409                           |
| POST /api/v1/budgets                        | Create without version; update requires current version; stale 409         |
| GET /api/v1/analytics/summary?month=2026-10 | Exact centavo totals, category expenses, budgets with versions             |
| POST /api/v1/imports/preview, /confirm      | Multipart; account, UTF-8 CSV; confirm requires digest and acknowledgement |

Example synthetic transaction body:

```json
{
  "account_id": 123,
  "occurred_at": "2026-10-01",
  "description": "Synthetic coffee",
  "category": "Food & dining",
  "kind": "expense",
  "amount": "0.03"
}
```

Cursor: supply both `before_date` and `before_id` from the last list entry. Live inserts before that cursor do not repeat older entries. Date edits may move records between pages; this is not a snapshot.

Version preconditions are a deliberate contract change in this increment; upgrade clients and UI alongside the backend. Owned stale writes return 409; missing budget/delete version returns 428; foreign resources remain 404. The UI reloads after conflicts. Validation returns field locations/types, never submitted values. Responses carry server-generated `X-Request-ID`. Total write body limit is 2 MB; CSV content limit remains 1 MB/5,000 rows. Amount grammar excludes exponents and more than two decimal places; no rounding is performed.
