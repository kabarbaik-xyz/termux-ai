# Training 5.2 — Claims vs Evidence + Small-PR Discipline
Audience: all devs. 90 minutes.
1. The rule: the AI's summary is testimony, not evidence. Evidence = diff + CI artifacts + Playwright report.
2. Drill: we show an AI reply claiming "fixed + tested" beside the actual diff/tests — find the three exaggerations.
3. Review flow: read AC → read diff against AC → run the spec yourself → then the AI's explanation, last.
4. Small-PR habit: >400 lines → bounce with "decompose", never "I'll review it anyway".
5. Red flags: sweeping refactors inside feature PRs; tests that assert mocks; "trust me" summaries without artifact links.
