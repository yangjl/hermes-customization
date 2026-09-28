# Historical Build completion correction

User feedback on the running DBTL panel: previous Build results should be done.
The prior onboarding represented completed experiments as Design reconstruction
reviews because there was no historical import mode. This is a status correction
to the existing approved MVP hierarchy, not a new page or interaction workflow.

Use the existing native Kanban completion API and an auditable historical-build
receipt. Display the retained card in Build as Completed, distinguish original
experiment date from current recording date, preserve all submitted evidence,
and keep historical completion separate from approval for new work. Native
task body remains the original reconstruction assignment; phase projection is
derived from the completion receipt. No new task database or background worker.

Acceptance: historical manifests and their indirect source files are checked;
missing/changed evidence fails closed; ordinary planning cannot be completed
through this command without historical evidence; duplicate import and native
dependent edges are refused; historical receipts cannot authorize downstream
work; original approval workflow and role configuration remain intact.

Verification: isolated native-board tests, complete Python and Node suites,
read-only browser check of the real panel at desktop/narrow widths, and code
review. Existing source/installed plugin changes are preserved. No commit/push.

## Verification evidence

```text
python -m unittest discover -s tests
Ran 134 tests in 66.548s
OK

node --test tests/*.test.mjs
# tests 19
# pass 19
# fail 0
```

Eight targeted integration checks cover historical completion, preserved
submission/no approval, approved-parent refusal, stale indirect files, wrong
coordinator, future date, ordinary planning, downstream edges, and unchanged
human approval behavior. Independent code review found no actionable issues.

Read-only browser verification against the live panel passed: seven Build cards
with Completed badges, one Design/review card, historical detail without an
approval button, keyboard selection, narrow layout and zero browser errors.
Desktop and narrow screenshots were personally inspected: same existing
four-lane hierarchy and decision banner, with Completed replacing Approved
only for historical Builds. The existing approved interface remains otherwise
unchanged. This browser check does not verify packaged-app tab focus or external
harness execution.

Installed using install.sh --codex-dbtl-only and refreshed the Codex package
with codex plugin add. Source and installed backend/assets matched.
No commit or push performed.
