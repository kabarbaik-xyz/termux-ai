# Tokens Convention
- ONE file: `design/tokens.json`. Figma variables are the source (free Starter + REST); `figma-tokens` syncs → PR diff.
- Token name in Figma == token name in JSON == CSS var/Tailwind theme key. Rename = coordinated change (skill does it).
- Code imports tokens only — grep-audited by CI (no hex/px where a token exists). New client = new token set, same components.
