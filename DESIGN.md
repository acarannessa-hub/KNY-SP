---
name: Kaya Natin! Youth – Candelaria
description: Public transparency site and officers' portal for a youth organization in Candelaria.
colors:
  civic-purple: "#7562b5"
  civic-purple-deep: "#5d4b9a"
  lagoon-cyan: "#55b8c7"
  lagoon-cyan-deep: "#31818c"
  field-green: "#82b96b"
  field-green-deep: "#5b8a49"
  sunlit-yellow: "#d8cf65"
  lavender-wash: "#e9e3f5"
  lagoon-wash: "#e2f2f3"
  field-wash: "#e7f2e2"
  ink-slate: "#30323d"
  quiet-slate: "#68717d"
  desk-white: "#f7f8fa"
  paper-white: "#ffffff"
  alert-rose: "#a94f5a"
  alert-rose-ink: "#7d3640"
  alert-rose-wash: "#f5e5e8"
  caution-amber-ink: "#6b4a0b"
  caution-amber-wash: "#fbf0d9"
  success-ink: "#315c37"
  lagoon-ink: "#1f5f69"
  sidebar-white: "#fbfaff"
typography:
  headline:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "clamp(30px, 4vw, 42px)"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  section:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.3
  figure:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "24px"
    fontWeight: 800
    lineHeight: 1.2
    fontFeature: "tnum"
  body:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  ui:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.2
  meta:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI, Aptos, Arial, Helvetica, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "0.03em"
rounded:
  control: "8px"
  card-public: "10px"
  card: "12px"
  dialog: "16px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "14px"
  md: "20px"
  lg: "26px"
  xl: "44px"
components:
  button-primary:
    backgroundColor: "{colors.civic-purple}"
    textColor: "{colors.paper-white}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.civic-purple-deep}"
  button-secondary:
    backgroundColor: "{colors.lavender-wash}"
    textColor: "{colors.civic-purple-deep}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "42px"
  button-secondary-hover:
    backgroundColor: "{colors.lagoon-wash}"
  button-danger:
    backgroundColor: "{colors.alert-rose-wash}"
    textColor: "{colors.alert-rose-ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  input-text:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink-slate}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    height: "44px"
  card:
    backgroundColor: "{colors.paper-white}"
    rounded: "{rounded.card}"
    padding: "26px"
  pill-paid:
    backgroundColor: "{colors.field-wash}"
    textColor: "{colors.success-ink}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  pill-unpaid:
    backgroundColor: "{colors.alert-rose-wash}"
    textColor: "{colors.alert-rose-ink}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  table-header:
    backgroundColor: "{colors.lavender-wash}"
    textColor: "{colors.civic-purple-deep}"
    typography: "{typography.label}"
---

# Design System: Kaya Natin! Youth – Candelaria

## Overview

**Creative North Star: "The Bright Civic Desk"**

A cheerful but businesslike workspace. The organization's four official colors bring youthful energy, but they sit on a clean, efficient desk: near-white surfaces, slate text, generous whitespace and orderly tables. Color guides the eye to what matters (the main action, a status, a total) and never competes with the numbers. The same world serves two audiences. The public site is open and welcoming for neighbors and sponsors checking where money goes. The officers' portal is a calm place where volunteers record, review and approve records between activities.

Surfaces are friendly and soft: rounded corners, gentle ambient shadows, and a small lift on hover tell people what is clickable without shouting. Density is moderate. Tables carry most of the portal's information, with sticky purple-tinted headers, right-aligned tabular figures and quiet row stripes. Forms open in centered dialogs rather than inline accordions.

**Key Characteristics:**
- Four official brand colors (purple, cyan, green, yellow), led by purple, on near-white.
- Slate ink, never pure black; muted slate for secondary text.
- Soft, lifted cards (12px radius, ambient shadow) and 8px-rounded controls.
- Status is always a tinted pill: green wash for good, rose for problems, amber for caution, cyan for in-between.
- One system font stack (Segoe UI / Aptos), with bold weights doing the hierarchy work.

## Colors

The four official organization colors, each paired with a deep shade for text and a pale wash for backgrounds, on a white-and-slate desk.

### Primary
- **Civic Purple** (#7562b5): the organization's lead color. Default buttons, active highlights, the brand mark.
- **Civic Purple Deep** (#5d4b9a): headings, links, table header text, secondary-button text, button hover. The "voice" color for anything that reads as a title.

### Secondary
- **Lagoon Cyan** (#55b8c7): partner to purple in the signature gradient (primary buttons, the Logout pill, the brand mark), focus rings and input focus borders.
- **Lagoon Cyan Deep** (#31818c): cyan used as text on light backgrounds (public site accents).

### Tertiary
- **Field Green** (#82b96b) and **Field Green Deep** (#5b8a49): success and money-in signals; the third stop of the brand-mark gradient; green-accent public pages.
- **Sunlit Yellow** (#d8cf65): the fourth official color. Used sparingly as a highlight on the public site; never for text.

### Neutral
- **Ink Slate** (#30323d): body text and strong labels.
- **Quiet Slate** (#68717d): descriptions, hints, secondary table text.
- **Desk White** (#f7f8fa): page background, under a pale lavender gradient at the top of portal pages.
- **Paper White** (#ffffff): cards, dialogs, inputs, table rows.
- **Washes**: Lavender (#e9e3f5) for table headers, secondary buttons and hover fills; Lagoon (#e2f2f3) and Field (#e7f2e2) for tinted states.
- **Status inks and washes**: Alert Rose (#7d3640 on #f5e5e8; solid #a94f5a for danger hover and negative money), Caution Amber (#6b4a0b on #fbf0d9), Success (#315c37 on the field wash), Lagoon ink (#1f5f69 on the lagoon wash for in-between states).
- **Sidebar White** (#fbfaff): the portal sidebar, one step warmer than the page so navigation reads as its own layer.
- **Hairline** (rgba(48, 50, 61, 0.1)): card borders, input borders, dividers.

### Named Rules
**The Official Four Rule.** Purple, cyan, green and yellow are the organization's official colors. Keep them; don't introduce a new hue for decoration. New states use the existing washes and inks.

**The Wash-Not-Fill Rule.** Status and secondary emphasis use a pale wash with a deep ink of the same hue (for example #315c37 on #e7f2e2). Saturated fills are reserved for the primary action and the brand gradient.

## Typography

**Display Font:** Segoe UI (with Aptos, Arial, Helvetica, sans-serif)
**Body Font:** the same stack
**Label/Mono Font:** the same stack; figures use tabular numerals

**Character:** One familiar system face that feels native on the Windows laptops and phones officers already use. Hierarchy comes from weight (700–800) and the purple-deep heading color rather than from a second typeface.

### Hierarchy
Every size comes from a CSS variable in `private.css` (`--type-headline` … `--type-label`); no literal font sizes outside the ramp.
- **Headline** (800, clamp(30px, 4vw, 42px), 1.15, -0.025em): every page title (h1), in Civic Purple Deep.
- **Section** (700, 22px, 1.25): every h2: card, toolbar and dialog headings.
- **Title** (700, 18px, 1.3): h3 and the brand name.
- **Figure** (800, 24px, tabular numerals): stat tiles and finance totals.
- **Body** (400, 16px, 1.6): paragraphs and table cells; page descriptions are capped near 60–72ch in Quiet Slate.
- **UI** (700, 14px, 1.2): buttons, navigation links, table actions.
- **Meta** (400, 13px, 1.5): field hints, the back link, filter menus, audit details.
- **Label** (700, 12px, 0.03em, uppercase): stat labels, column headers, pills (800).

### Named Rules
**The Numbers Line Up Rule.** Money and counts always use tabular numerals, right-aligned in tables, with ₱ and two decimals.

**The Clear Step Rule.** Adjacent heading roles differ by at least one clear step (42 → 22 → 18 → 16). Headings wrap balanced, paragraphs wrap pretty; never add a new size without adding it to the ramp.

## Layout

**Portal (Operate).** A fixed 256px sidebar on the left (Sidebar White, hairline right edge) and a content column up to 1180px wide beside it, with 32px top padding. The sidebar groups every destination by job: Overview; Finances; People; Communication; Records. The current page is a lavender pill. The signed-in person and Password / Log out sit at the bottom. Below 960px the sidebar becomes an off-canvas drawer opened from a sticky top bar with a menu button; a dimmed scrim closes it, as does Escape.

Every portal page uses the same skeleton: an optional back link (only on true sub-pages, e.g. a ledger back to Finance overview), the page header (title and one-line purpose on the left, stat tiles on the right, the most important tile tinted lavender), flash messages, then white **panels**. The Overview page is a two-column grid (attention, activity and totals on the left; coming up and shortcuts on the right) that stacks below 1100px. Stat tiles become a two-column grid on phones.

**Public site (Persuade / Read).** A sticky white header topped by the four-color ribbon, a 1160px centered column, and full-width sections separated by hairlines, alternating white and Desk White. Inner pages open with a page header band (breadcrumb, title, lead paragraph, left-aligned). Long documents (Introduction, Constitution) use a sticky contents list beside the text, which folds above it on narrow screens. Prose is capped near 68ch.

Spacing runs on a 4px base: 4, 8, 12, 16, 24, 32, 48, 72, 104px (`--space-*` in the portal, `--s1`–`--s9` on the public site).

### Named Rules
**The One Way There Rule.** Every destination has exactly one place in navigation. Don't add tab strips or "back to dashboard" links that repeat the sidebar.

**The Attention First Rule.** The Overview page leads with what needs a decision (waiting requests, missing emails, sync problems), not with links to every module.

## Elevation & Depth

A soft, lifted hybrid. Cards and the header float slightly on ambient slate-tinted shadows. Hover raises interactive cards and buttons by 1–2px with a stronger shadow. Dialogs sit well above the page on a deep shadow over a dimmed slate backdrop. Tables and inputs stay flat.

### Shadow Vocabulary
- **Resting card** (`box-shadow: 0 10px 28px rgba(48, 50, 61, 0.08)`): cards, header row, summary tiles.
- **Lifted card** (`box-shadow: 0 16px 34px rgba(48, 50, 61, 0.13)`): card hover.
- **Header** (`box-shadow: 0 8px 24px rgba(48, 50, 61, 0.06)`): sticky top bar, with an 8px backdrop blur.
- **Button hover** (`box-shadow: 0 5px 12px rgba(93, 75, 154, 0.2)`): purple-tinted lift under buttons.
- **Dialog** (`box-shadow: 0 24px 60px rgba(48, 50, 61, 0.28)`): modal forms over a rgba(48, 50, 61, 0.45) backdrop.

### Named Rules
**The Gentle Lift Rule.** Only things you can click lift on hover (1px for buttons, 2px for cards). Static content never moves.

## Shapes

Consistently rounded, never sharp, never blobby: 8px on controls (buttons, inputs, nav links, menus), 12px on portal cards (10px on public cards), 16px on dialogs, full pills for statuses and counts. Borders are 1px hairlines in slate at 8–10% opacity. The brand mark is a 46px rounded square (12px) filled with the purple-to-cyan-to-green gradient.

## Components

### Buttons
Friendly, solid and confident.
- **Shape:** gently rounded (8px), at least 42px tall (34px for the small size), bold 14px labels.
- **Primary:** the purple-to-cyan gradient (135deg) with white text; hover deepens to purple-deep to purple.
- **Default:** solid Civic Purple; hover Civic Purple Deep with a 1px lift and a purple shadow.
- **Secondary:** Lavender wash with purple-deep text; hover shifts to the Lagoon wash.
- **Danger:** Rose wash with rose ink; hover fills solid rose (#a94f5a) with white text.
- **Link button:** transparent, purple-deep bold text, lavender wash on hover; used for row actions such as Edit.

### Chips / Pills
- **Style:** full pill, 12px bold, wash background with matching deep ink.
- **States:** Paid or Active (field wash), Partial or Waiting (lagoon wash), Unpaid, Inactive or Rejected (rose wash), Deferred or Expired (amber wash), roles (lavender for admin, lagoon for encoder, gray for viewer).

### Cards / Containers
- **Corner Style:** 12px (portal), 10px (public).
- **Background:** near-opaque white (rgba(255, 255, 255, 0.97)).
- **Shadow Strategy:** resting card shadow; lifted on hover only when the card is interactive.
- **Border:** 1px hairline.
- **Internal Padding:** 26px.

### Inputs / Fields
- **Style:** white, 1px hairline border, 8px radius, 44px minimum height, labels above in bold.
- **Focus:** the border turns Lagoon Cyan with a 3px soft cyan ring (rgba(85, 184, 199, 0.18)); keyboard focus elsewhere shows a 3px cyan outline.
- **Hints and errors:** hints in 13px Quiet Slate below the field; errors arrive as rose flash messages at the top of the page.

### Navigation
- **Portal sidebar:** 14px semibold links with an outline icon each (one consistent 1.75-stroke set in `templates/_icons.html`), uppercase 12px group labels, a lavender pill and purple icon for the current page, a purple count badge for waiting export requests. Icons are drawn SVG, never emoji or glyphs.
- **Public header:** brand mark and name, then Home, About (a dropdown for Introduction, Constitution, Best practices, Roster), Advocacies, Events, Transparency, and a gradient "Contact us" button. The current page is a lavender pill. On phones it collapses to a menu button revealing the same links grouped.

### Panels
The portal's standard container: white, 1px hairline, 12px corners, a barely-there shadow (0 1px 2px), 24px padding, and a header row (Section-size title on the left, one secondary action on the right). Tables inside a panel run edge to edge. Panels never lift on hover.

### Attention List (signature, portal Overview)
Rows on a pale lavender-gray tint, each with a 34px tinted icon square (amber for things to act on, lagoon for information), one plain sentence, and one small secondary button naming the action ("Review", "Add emails"). When nothing needs attention it says "All clear" in success green.

### Money Ledger Card (signature, public home)
A white card beside the hero listing each income source, expenses as a negative, then a heavy rule and the balance in large purple figures, with the latest-entry date and a link to the full breakdown. It is the public face of The Open Record: real totals, never names.

### Ledger Table (signature)
The portal's main workhorse: a white card with a toolbar, then a full-width table whose header row is lavender with purple-deep, letter-spaced column titles. Every column title is a button with a ▾ that opens a sort-and-filter menu. Money columns are right-aligned tabular figures, empty cells show a pale "—", and row actions (Edit, Delete) sit right-aligned as link buttons. A stat strip in the page header (uppercase labels over 24px Figure numbers) updates live as filters change.

### Dialogs
Centered modal cards (16px radius, up to 680px wide, 480px for confirmations) with a header row (Section-size purple-deep title and a round × close button), a scrolling body and a footer with Cancel and the main action. All add, edit, delete and confirm flows use dialogs, not inline forms.

## Do's and Don'ts

### Do:
- **Do** lead with Civic Purple (#7562b5) and reserve the purple-to-cyan gradient for the single most important action on a screen, the Logout pill and the brand mark.
- **Do** show every status as a wash-and-ink pill from the existing set.
- **Do** right-align money in tables with tabular numerals, ₱ and two decimals.
- **Do** put add, edit and confirm forms in dialogs with Cancel on the left and the action on the right.
- **Do** keep page titles in Civic Purple Deep and descriptions in Quiet Slate.
- **Do** put new portal pages in the sidebar group that matches the job, and build them from the page header + panels skeleton.
- **Do** publish real totals wherever the public site shows money; show an empty state, never a fake ₱0.00 placeholder.
- **Do** use the 8 / 12 / 16px radius ladder and the 1px slate hairline for borders.

### Don't:
- **Don't** add hues outside the official four plus the neutral and status palette.
- **Don't** use pure black text or pure gray borders; use Ink Slate and the slate hairline.
- **Don't** set yellow (#d8cf65) as text or as a large fill; it is a highlight only.
- **Don't** make static content move on hover; only clickable elements lift.
- **Don't** go back to inline expand-to-edit forms in tables; use the dialog pattern.
- **Don't** put a colored bar along one edge of a rounded card, or a small uppercase label above a heading.
- **Don't** give each public page its own inline stylesheet; everything public lives in `public_site/static/css/public.css`.
