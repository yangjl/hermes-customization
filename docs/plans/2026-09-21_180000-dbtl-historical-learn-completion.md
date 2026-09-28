# Restore historical Learn results

User feedback on the working historical Build panel: "how about learn results?"
Preserve the same approved four-lane layout and completion semantics. Add a
separate completed Learn record with an Open source Build link. No new workflow
page, controls for scientific approval, task database, or external worker.

Reuse the historical completion receipt machinery, with a distinct
historical-learning-snapshot manifest identifying original learning outputs.
Require a completed same-cycle historical Build and pin its submission ID.
Propagate stale evidence from both sources. Keep normal approvals unchanged,
current role defaults untouched, and historical completion ineligible as an
approved execution parent.

Verify isolated native-board behavior including same-cycle linkage, stale
upstream and local evidence, source completeness and no approval/role change.
Run full Python and Node suites; inspect live desktop/narrow screenshots and
keyboard navigation to the source Build. Do not commit or push.

## Verification evidence

```text
python -m unittest discover -s tests
Ran 139 tests in 56.748s
OK

node --test tests/*.test.mjs
# tests 19
# pass 19
# fail 0
```

Thirteen targeted history checks pass, including Learn source identification,
same-cycle Build linkage, upstream/local staleness and no approval or role change.
Independent code review found no actionable issues.

Read-only live browser verification passed: seven Learn/Completed cards, seven
Build/Completed cards, one Design/review card, source-Build navigation, no approval
control on historical Learn, keyboard selection, narrow layout and zero browser
errors. Desktop and narrow screenshots were personally inspected; the existing
lane hierarchy is preserved and Learn outputs are visible separately from Build.
The check covers the local web panel, not packaged-app tab focus.

Installed through the existing installer and refreshed the Codex package;
source and installed code matched. No commit or push.
