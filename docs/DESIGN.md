# SupportPilot design system

SupportPilot is a dense, dark operations tool for support and engineering teams. The interface should feel like Linear or Vercel: quiet surfaces, one accent, precise type, and status that reads at a glance. The ticket, its evidence, and the reviewer's decision stay the visual focus. Chrome stays in the background.

## Principles

1. **Content over chrome.** Surfaces differ by one or two neutral steps. Borders are hairlines. No decorative gradients inside the app shell. The sign-in screen is the one place where the brand gets to show off.
2. **One accent, used for intent.** Emerald marks the primary action, the active nav item, and positive state. Everything else is neutral or a semantic status color.
3. **Honest data.** Metrics describe real workspace or selected-run data. Unknown values render as `—` or "Unknown", never as invented numbers.
4. **Keyboard first.** Every view is reachable from the ⌘K command palette. Focus is always visible.
5. **Human in the loop.** Drafts, agent runs, and GitHub writes are visibly proposals until a person acts.

## Tokens

All colors live in `frontend/src/styles.css` above the `/* @tokens-end */` marker. **Below that marker, no raw hex values are allowed.** Use `var(--token)` or `color-mix(in oklab, var(--token) N%, transparent)` for translucency.

### Neutral scale

| Token | Hex | Use |
| --- | --- | --- |
| `--n-0` | `#09090b` | Page background |
| `--n-1` | `#0e0f11` | Sidebar, auth story panel |
| `--n-2` | `#131417` | Cards, inputs |
| `--n-3` | `#18191d` | Hover, raised rows, popovers |
| `--n-4` | `#1f2024` | Card borders, dividers, active nav |
| `--n-5` | `#27282d` | Default control borders |
| `--n-6` | `#323339` | Strong borders, hover borders |
| `--n-7` | `#45464e` | Disabled text, separators on raised surfaces |
| `--n-8` | `#63646d` | Captions, icons at rest |
| `--n-9` | `#8b8c95` | Secondary text |
| `--n-10` | `#b1b2ba` | Body text on dense views |
| `--n-11` | `#d8d9de` | Labels, emphasized body |
| `--n-12` | `#f4f4f5` | Headings and primary text |

### Semantic families

Each family has four steps: `-bg` (tinted fill), `-border`, the solid color, and `-soft` (text on a tinted fill).

| Family | Solid | Meaning |
| --- | --- | --- |
| `accent` | `#34d399` | Primary action, success, connected, resolved |
| `warn` | `#f5b544` | Waiting, fixture or demo mode, needs information |
| `danger` | `#f87171` | Failure, rejected, destructive |
| `violet` | `#a78bfa` | Identity, evidence, AI trace |
| `info` | `#60a5fa` | Neutral metadata, links, queued |
| `live` | `#22d3ee` | A genuinely running agent only (pulse, active pipeline stage) |

shadcn/ui variables (`--background`, `--card`, `--primary`, `--border`, …) are aliases onto these tokens, so the primitives in `src/components/ui` follow the system automatically.

## Typography

- **Family:** Geist Variable (UI) and Geist Mono Variable (IDs, code, logs), self-hosted through Fontsource so the production CSP keeps fonts same-origin.
- **Scale:** 11 (micro labels only) · 12 (captions, badges) · 13 (UI default: nav, buttons, table cells) · 14 (body, descriptions) · 16 (section titles) · 20 (dialog and form titles) · 24 (page titles) · 32–48 (sign-in headline only).
- **Minimum size is 11px.** Nothing below that.
- Headings use weight 600 and negative tracking (`-0.02em` to `-0.035em`). Numbers in metrics and counts use `font-variant-numeric: tabular-nums`.

## Spacing, radius, and elevation

- 4px base grid. Common steps: 4, 8, 12, 16, 20, 24, 32.
- Page gutter is the `--gutter` custom property on `.main-shell`: 48px at ≥1600px, 32px by default, 24px at ≤1200px, and 16px at ≤620px. The sticky topbar bleeds to the gutter edge using the same variable.
- Radius: 6px for nav items, 8px for controls and buttons, 12px (`rounded-xl`) for cards, 999px for pills.
- Elevation is the single `--shadow-lg`: a faint top highlight plus a soft drop shadow. Cards use it; nothing stacks shadows.

## Layout

```
┌────────────┬──────────────────────────────────────────────┐
│ Brand      │ Group › View              ● Mode  ⟳  + New   │ ← sticky, blurred topbar (56px)
│ ⌘K search  ├──────────────────────────────────────────────┤
│            │ Page title (24/600)                          │
│ Support    │ One-line description                         │
│  Overview  │                                              │
│  Tickets   │ ┌ metric ┐┌ metric ┐┌ metric ┐┌ metric ┐      │
│  Review ②  │ └────────┘└────────┘└────────┘└────────┘      │
│  Knowledge │ ┌ content cards … ─────────────────────────┐ │
│ Engineering│ │                                          │ │
│  Repos     │ └──────────────────────────────────────────┘ │
│  Agents    │                                              │
│ Workspace  │                                              │
│  …         │                                              │
│ [DE demo ⌄]│                                              │
└────────────┴──────────────────────────────────────────────┘
```

- **Sidebar (248px):** grouped navigation (Support, Engineering, Workspace), a ⌘K trigger, and an account menu at the bottom (settings, source, disconnect). It collapses into a dialog under 900px.
- **Sign-in:** a split screen. The left story panel has a radial accent glow, a masked grid, and three capability points. The right side holds a single 380px form. It stacks under 900px.
- **Ticket workbench:** three columns (inbox, detail, evidence/trace). It drops to two columns at 1200px and stacks at 620px.

## Components

shadcn/ui (new-york, Radix): Button, Badge, Card, Input, Textarea, Dialog, Tabs, Tooltip, Native Select, Separator, **Command** (cmdk palette), **Dropdown Menu** (account menu), **Avatar**, **Kbd**.

| Pattern | Rules |
| --- | --- |
| Primary button (`.primary`) | Accent fill, dark text, inset highlight, 36px tall (40px on the sign-in form). One per view region. |
| Status badge (`StateBadge`) | Outline badge colored by its family; label is snake_case humanized, and "CLI" stays uppercase. |
| Metric card | Label and icon on top, a 24–32px tabular value, and a one-line caption. The value is a button when it links to a filtered queue; its arrow is muted until hover. |
| Empty state | Icon tile, one-sentence title, one-sentence guidance, an optional single action. |
| Alerts | `role="alert"` for errors, `role="status"` for notices, always dismissible. |
| Command palette | ⌘K / Ctrl+K anywhere. Matches on view label and group. Includes actions (New ticket, Disconnect). |

## 21st.dev

The 21st.dev registry (`https://21st.dev/r/...`) and its MCP server require an API key (`API_KEY_21ST`). No key was configured during this build, so no 21st.dev components were installed. Their [dashboard collection](https://21st.dev/community/components/s/dashboard) was used only as a visual reference for metric-card and shell composition. To pull real catalog components later, set `API_KEY_21ST` for the 21st plugin, then install through `npx shadcn add` or the MCP `get_component` tool. Integrate them using the tokens above, not their bundled colors.

## Accessibility

- WCAG AA contrast: `--n-9` and lighter on `--n-0`/`--n-2` for text; `--n-8` only for icons and non-essential captions.
- Visible focus ring: 2px `--ring` (accent) with offset.
- Dialogs trap focus and restore it on close. Tabs support arrow keys (covered by Playwright).
- `prefers-reduced-motion` disables animations and transitions.
- No horizontal overflow at 390px width (covered by Playwright).

## Verification

```bash
npm --prefix frontend run build
npm --prefix frontend run test:browser   # 12 Chromium flows incl. ⌘K palette and mobile overflow
```
