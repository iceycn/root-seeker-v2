# Business-logic docs progress

Plan (round 1): `docs/superpowers/plans/2026-08-17-business-logic-traces.md`  
Plan (round 2 re-audit): `docs/superpowers/plans/2026-08-17-business-logic-reaudit.md`

## Round 1 (complete)

Tasks 1–20: all domain docs `01`–`19` + `00-overview.md` created.

## Round 2 re-audit (2026-08-17)

- Docs sync: 01, 02, 09, 10, 11, 16, 00-overview updated for current code
- Bug fix: Webhook `ChannelSecurity` wired via `ROOTSEEKER_WEBHOOK_SIGNING_SECRET` / `ROOTSEEKER_WEBHOOK_ALLOWLIST_IPS`
- Tests: `test_api_webhook_rejects_invalid_signature` added; full suite green

## Remaining known gaps (documented, not bugs)

- `waiting_approval` Case status not driven by approval flow
- `ToolPlanCall.timeout_seconds` not enforced in agent path
- `skill_system/rollback.py` not implemented (publisher deprecate/archive only)
- Cross-process `PresenceRegistry` is in-memory per process
