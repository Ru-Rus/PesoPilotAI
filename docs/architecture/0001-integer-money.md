# ADR 0001: Integer PHP centavos

Accepted. Store authoritative values as BIGINT centavos. Accept bounded decimal strings with up to two decimal places; reject exponents/rounding. SQL computes totals. This avoids floating-point drift and gives exact reconciliation. Multi-currency and transfer/refund semantics require separate design. UI formatting is presentation only.
