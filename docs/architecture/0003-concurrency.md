# ADR 0003: Versions and account locks

Accepted. Client-supplied current versions gate account/transaction/budget updates and transaction deletes. SQL Server account update locks serialize archival and finance posting; source/target IDs lock in stable order. Exact import repeat uniqueness remains transactional and advisory duplicate candidates preserve legitimate purchases. This trades concurrent writes within one account for predictable integrity. Broader load/deadlock measurements remain pending.
