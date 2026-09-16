<!-- DOC: course-spec | version=v__ | date=__ | upstream=approved proposal-v__ + curriculum.md v__ -->
# Course Experience Spec: <Field / Subject>

**Course id (slug):** `course-<…>`
**Authoritative inputs:** approved `docs/proposal/proposal-v<NN>.md` +
`docs/training/curriculum/curriculum.md`.

## 1. Scope & Assumptions
One paragraph: what this spec versions, the KBTI preset chosen (course on the
kbti-elearning platform — platform chrome is fixed, never rebranded), and any
assumptions taken where sources were silent.

## 2. Learner Journey (Mermaid)
One flowchart of the learner's path through the course (enroll → learn →
practice → assessment → completion).

## 3. Lesson Inventory
| # | Lesson id | Title | Type | Duration | Quiz | Outcome | Source lesson |
| :- | :-------- | :---- | :--- | :------- | :--- | :------ | :------------ |
| 1 | lesson-01-<slug> | <title> | reading | <mins> | <q count / –> | OU-<n> | docs/training/modules/module-<NN>/lesson-01-<slug>.md |

## 4. Quiz & Feedback Strategy
- Note | correct | options | explanation message, mapped to lessons.
  Quizzes ship ONLY in `course.json`; the platform renders them in the
  lesson's server-graded quiz panel (answers never reach the client) and
  gates completion via the "Mark complete" button — lesson bodies carry NO
  inline answer keys.

## 5. Visual System
Course-level tokens follow the **KBTI preset** (`design-tokens.json`: red
`#a11c1c` family, navy `#1a1a2e`, `bg #f7f6f5`, ok `#15803d`, warn
`#b45309`, cards radius 14px). The design targets the kbti-elearning lesson
app-shell: sidebar lesson index (type/duration tags), header pill + progress
bar + "Mark complete", framed reading surface, prev/next cards, dedicated
quiz panel, and the course cover panel. Content itself is style-neutral.

## 6. Design Tokens
Reference `design-tokens.json` (KBTI preset, colors + radius + shadow) — no
restatement.

## 7. Assumptions & Decisions
1. **Assumed:** <…> **Decision:** <…> **Rationale:** <…>