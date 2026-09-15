<!-- DOC: rollout | version=v__ | date=__ | upstream=qa/review-checklist.md v__ + course-spec.md v__ -->
# Rollout Plan: <Field / Subject>

## Go Decision
- **QA gate:** <pass/fail counts from docs/training/qa/review-checklist.md v__>
- **Course going live:** `course-<…>` (installed on kbti-elearning)

## Cohorts & Schedule
| Cohort | Segment | Start | End | Session cadence | Platform vs facilitated | Capacity |
| :----- | :------ | :---- | :-- | :-------------- | :-------------------- | :------- |
| C1 | <segment> | <date> | <date> | <cadence> | <mix> | <n> |

## Facilitation
Which sessions are facilitated, the facilitation-guide reference (or
"self-paced only"), and the facilitator-to-learner ratio.

## Comms & Prep
Learner announcements, prerequisites, expected time commitment, access URL on
the platform.

## Materials & Platform Checklist
- [ ] Course installed on the platform — `course-<…>` (link)
- [ ] <handout/print materials>
- [ ] <facilitator prep>
- [ ] Cohort invites sent

## Success Metrics
| KBI | Measurement | Target | Owner |
| :-- | :---------- | :----- | :---- |
| <curriculum KBI> | <completion / assessment pass / observed behavior> | <target> | <owner> |

## Risk Register
| Risk | Mitigation |
| :--- | :--------- |

## Iteration Loop
How learner/assessment data returns to the course: trigger → `learning-qa`
re-run → package update → reinstall (same course id), at a stated cadence
(e.g. after each cohort).

## Assumptions
1. **Assumed:** <…> **Decision:** <…>