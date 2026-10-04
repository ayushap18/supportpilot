# SupportPilot interface

Build a dark support operations workspace with charcoal surfaces, emerald actions, restrained violet trace accents, and readable typography. Keep visual hierarchy focused on the ticket, draft, evidence, and reviewer decision.

## Implementation sequence

1. Configure Tailwind CSS and install real shadcn/ui primitives.
2. Refresh the application shell, connection screen, and responsive navigation.
3. Style the inbox, investigation, source cards, trace, and review controls as one coherent workspace.
4. Replace the custom modal and tabs with accessible primitives; add actual selected-run metrics and progress indicators.
5. Verify keyboard navigation, mobile overflow, production security headers, ticket creation, investigation, and approval before publishing the changes to GitHub.

## Components and references

- shadcn/ui: Button, Badge, Card, Input, Textarea, Dialog, Tabs, Tooltip, Native Select, Separator.
- [21st.dev dashboard collection](https://21st.dev/community/components/s/dashboard): public visual references for dashboard composition.
- [ReUI Statistics Card 7 on 21st.dev](https://21st.dev/@sean0205/components/statistics-card-7): reference for segmented metric cards with labels, values, and supporting context. SupportPilot uses original markup and real selected-run data rather than the sample financial metrics.

No 21st.dev MCP tool is connected in this environment. Public references are used for design direction; no paid registry installation or MCP call is claimed.

## Constraints

- Fixture mode remains clearly labeled as deterministic routing and lexical retrieval.
- Metrics describe the selected investigation, not invented workspace analytics.
- Tokens stay in memory; all review actions preserve the existing API behavior.
- Controls support focus visibility, sufficient contrast, and reduced motion.
- Narrow screens stack the workbench and expose navigation through an accessible dialog.
- Production CSP keeps scripts and fonts restricted to the same origin. Inline CSS elements and style attributes are allowed for Radix positioning and modal scroll locking; untrusted text is rendered through React escaping. Browser checks exercise this deployed policy.
