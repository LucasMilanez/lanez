<!--
Keep the title as a Conventional Commit: `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `chore:`. For breaking changes add `!` before the colon.
-->

## Summary

<!-- What does this change do and why? One or two sentences. -->

## Details

<!-- Optional longer explanation, design notes, tradeoffs. -->

## Testing

<!--
How did you validate this?
- Backend: `pytest` output (full suite or the relevant module)
- Frontend: `npm test` / manual browser check
- Deploy: smoke test steps if the change touches infra
-->

## Checklist

- [ ] Tests added or updated
- [ ] `pytest` passes locally
- [ ] `npm run build` succeeds
- [ ] Docs / `.env.example` updated if the change introduces or renames a
      config option
- [ ] No secrets, tokens or PII in code or fixtures
- [ ] PR is scoped to a single concern
