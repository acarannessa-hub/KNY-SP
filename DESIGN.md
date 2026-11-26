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
  public-violet: "#7562b5"
  public-lagoon: "#1fa2b8"
  public-leaf: "#5a9e3c"
  public-gold: "#e7bf1e"
  public-indigo: "#3f2c8c"
  public-teal: "#0b7485"
  public-forest: "#2f6e2c"
  public-night: "#1b1d29"
  public-text-violet: "#6650a8"
  public-text-lagoon: "#0e7c8f"
  public-text-leaf: "#3d7a29"
  public-text-gold: "#8a6d00"
  public-text-pink: "#b8397a"
  public-display-cyan: "#1897ab"
  public-ink-2: "#4a4f5e"
  public-platform: "#ffffff"
  public-platform-2: "#f4f4f7"
  public-pastel-violet: "#dccfff"
  public-pastel-pink: "#ffd2ef"
  public-pastel-lagoon: "#c4f1f4"
  public-pastel-mint: "#d4f6d6"
  public-pastel-butter: "#fff3b8"
  public-sky: "#f8f6ff"
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
  public-hero-name:
    fontFamily: "Nunito, Segoe UI, sans-serif"
    fontSize: "clamp(58px, 15vw, 108px)"
    fontWeight: 1000
    lineHeight: 0.95
    letterSpacing: "-0.035em"
  public-h1:
    fontFamily: "Nunito, Segoe UI, sans-serif"
    fontSize: "clamp(38px, 5.6vw, 76px)"
    fontWeight: 900
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  public-h2:
    fontFamily: "Nunito, Segoe UI, sans-serif"
    fontSize: "clamp(26px, 3vw, 38px)"
    fontWeight: 800
    lineHeight: 1.08
    letterSpacing: "-0.015em"
  public-h3:
    fontFamily: "Nunito, Segoe UI, sans-serif"
    fontSize: "20px"
    fontWeight: 750
    lineHeight: 1.25
  public-tagline:
    fontFamily: "Nunito, Segoe UI, sans-serif"
    fontSize: "clamp(18px, 2.2vw, 24px)"
    fontWeight: 800
    lineHeight: 1.3
  public-lead:
    fontFamily: "Figtree, Segoe UI, Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: 1.55
  public-body:
    fontFamily: "Figtree, Segoe UI, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  public-ui:
    fontFamily: "Figtree, Segoe UI, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "0.01em"
  public-meta:
    fontFamily: "Figtree, Segoe UI, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.35
  public-label:
    fontFamily: "Figtree, Segoe UI, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 800
    letterSpacing: "0.1em"
rounded:
  control: "8px"
  card: "12px"
  dialog: "16px"
  pill: "999px"
  public-field: "12px"
  public-tile: "18px"
  public-frame: "20px"
  public-panel: "24px"
  public-banner: "28px"
spacing:
  xs: "8px"
  sm: "14px"
  md: "20px"
  lg: "26px"
  xl: "44px"
  public-gutter: "24px"
  public-block: "32px"
  public-stack: "48px"
  public-section: "72px"
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
  public-button-primary:
    backgroundColor: "{colors.public-violet}"
    textColor: "{colors.public-platform}"
    typography: "{typography.public-ui}"
    rounded: "{rounded.pill}"
    padding: "12px 22px"
    height: "50px"
  public-button-primary-home:
    backgroundColor: "{colors.public-text-violet}"
    textColor: "{colors.public-platform}"
    typography: "{typography.public-ui}"
    rounded: "{rounded.pill}"
    padding: "12px 22px"
    height: "50px"
  public-button-primary-home-hover:
    backgroundColor: "{colors.public-indigo}"
  public-button-ghost:
    backgroundColor: "{colors.public-platform}"
    textColor: "{colors.public-night}"
    typography: "{typography.public-ui}"
    rounded: "{rounded.pill}"
    padding: "12px 22px"
    height: "50px"
  public-button-ghost-hover:
    backgroundColor: "{colors.public-night}"
    textColor: "{colors.public-platform}"
  public-nav-cta:
    backgroundColor: "{colors.public-night}"
    textColor: "{colors.public-platform}"
    typography: "{typography.public-ui}"
    rounded: "{rounded.pill}"
    padding: "10px 18px"
  public-destination-banner:
    backgroundColor: "{colors.public-platform}"
    textColor: "{colors.public-night}"
    rounded: "{rounded.public-banner}"
    padding: "16px 24px 16px 16px"
  public-destination-banner-primary:
    backgroundColor: "{colors.public-text-violet}"
    textColor: "{colors.public-platform}"
    rounded: "{rounded.public-banner}"
    padding: "24px 24px 24px 16px"
  public-destination-banner-primary-hover:
    backgroundColor: "{colors.public-indigo}"
  public-page-head:
    backgroundColor: "{colors.public-sky}"
    textColor: "{colors.public-night}"
    typography: "{typography.public-h1}"
    padding: "72px 0 48px"
  public-panel:
    backgroundColor: "{colors.public-platform}"
    rounded: "{rounded.public-panel}"
    padding: "32px"
  public-input:
    backgroundColor: "{colors.public-platform}"
    textColor: "{colors.public-night}"
    typography: "{typography.public-body}"
    rounded: "{rounded.public-field}"
    padding: "12px 14px"
    height: "50px"
  public-footer:
    backgroundColor: "{colors.public-night}"
    textColor: "{colors.public-platform}"
    padding: "72px 0 24px"
---

# Design System: Kaya Natin! Youth – Candelaria

## Overview

This project carries two worlds that share one organization and its four official colors. The **officers' portal** (`templates/`, `static/css/private.css`) is a calm workspace. The **public website** (`public_site/templates/`, `public_site/static/css/public.css`) is the organization's logo made into a place. Each world's rules apply only inside its own templates and stylesheet; never mix their tokens.

**Creative North Star (portal): "The Bright Civic Desk"**

A cheerful but businesslike workspace. The organization's four official colors bring youthful energy, but they sit on a clean, efficient desk: near-white surfaces, slate text, generous whitespace and orderly tables. Color guides the eye to what matters (the main action, a status, a total) and never competes with the numbers. The officers' portal is a calm place where volunteers record, review and approve records between activities.

Surfaces are friendly and soft: rounded corners, gentle ambient shadows, and a small lift on hover tell people what is clickable without shouting. Density is moderate. Tables carry most of the portal's information, with sticky purple-tinted headers, right-aligned tabular figures and quiet row stripes. Forms open in centered dialogs rather than inline accordions.

**Key Characteristics (portal):**
- Four official brand colors (purple, cyan, green, yellow), led by purple, on near-white.
- Slate ink, never pure black; muted slate for secondary text.
- Soft, lifted cards (12px radius, ambient shadow) and 8px-rounded controls.
- Status is always a tinted pill: green wash for good, rose for problems, amber for caution, cyan for in-between.
- One system font stack (Segoe UI / Aptos), with bold weights doing the hierarchy work.

**Creative North Star (public site): "The Logo in Its Own Countryside"**

The public site takes its light from the organization's logo: an iridescent pastel field (lavender, lagoon, butter, mint, pink) over a fine white grid, forward chevrons drawn in the four official colors, and chunky rounded Nunito type. The home page stands the full name, "Kaya Natin! Youth – Candelaria", over a pixel-art Candelaria countryside of hills, rice-field rows, a glowing sun and swaying coconut palms, then offers four poster-style destination banners with About first. The countryside is pixel art in the idiom of the organization's own posters, set against the smooth holographic light.

Every inner page is a line in one color of the palette (violet, indigo, teal, forest, leaf, gold, lagoon, ink). That color tints the holographic page head, fills the chevron section markers, the current section tab and the primary button. Behind each page head runs a full-bleed, animated pixel-art scene of the page's subject, in a Candelaria town of houses, shops and streets, peopled by small pixel-art youth in everyday clothes. The home sky follows the visitor's clock. Containers are generously rounded (20–28px), borders are soft hairlines, and the site closes on a dark ink footer under the four-color ribbon. Professional and colorful, never cutesy: no script faces, no mascots, no glyph icons.

**Key Characteristics (public site):**
- Iridescent pastel radial washes over a 40–44px white grid, on the home hero and every page head.
- The drawn chevron (a clip-path shape, never a glyph) in violet, lagoon, leaf and gold.
- Nunito 800–1000 for display, Figtree for text, both from Google Fonts.
- One line color per page, with text-safe deeper steps wherever color carries type.
- Pill buttons with a drawn arrowhead; rounded 20–28px containers; hairline borders.
- A pixel-art countryside (crisp-edged hills and coconut palm sprites) in the posters' idiom on home, and a moving pixel-art scene behind every inner page head.
- Home changes with the time of day: morning, day, sunset, night.
- Slow, quiet motion (float, sway, glow) that stops entirely under reduced motion.

## Colors

The four official organization colors in two tunings: soft with washes and inks for the portal desk, and saturated logo light with text-safe steps for the public site.

### Primary
- **Civic Purple** (#7562b5): the organization's lead color. Default buttons, active highlights, the brand mark.
- **Civic Purple Deep** (#5d4b9a): headings, links, table header text, secondary-button text, button hover. The "voice" color for anything that reads as a title.

### Secondary
- **Lagoon Cyan** (#55b8c7): partner to purple in the signature gradient (primary buttons, the Logout pill, the brand mark), focus rings and input focus borders.
- **Lagoon Cyan Deep** (#31818c): cyan used as text on light backgrounds.

### Tertiary
- **Field Green** (#82b96b) and **Field Green Deep** (#5b8a49): success and money-in signals; the third stop of the brand-mark gradient.
- **Sunlit Yellow** (#d8cf65): the fourth official color. Used sparingly as a highlight; never for text.

### Neutral
- **Ink Slate** (#30323d): body text and strong labels.
- **Quiet Slate** (#68717d): descriptions, hints, secondary table text.
- **Desk White** (#f7f8fa): page background, under a pale lavender gradient at the top of portal pages.
- **Paper White** (#ffffff): cards, dialogs, inputs, table rows.
- **Washes**: Lavender (#e9e3f5) for table headers, secondary buttons and hover fills; Lagoon (#e2f2f3) and Field (#e7f2e2) for tinted states.
- **Status inks and washes**: Alert Rose (#7d3640 on #f5e5e8; solid #a94f5a for danger hover and negative money), Caution Amber (#6b4a0b on #fbf0d9), Success (#315c37 on the field wash), Lagoon ink (#1f5f69 on the lagoon wash for in-between states).
- **Sidebar White** (#fbfaff): the portal sidebar, one step warmer than the page so navigation reads as its own layer.
- **Hairline** (rgba(48, 50, 61, 0.1)): card borders, input borders, dividers.

### Public Site: Official Four (logo light)
- **Logo Violet** (public-violet): the first chevron, "Kaya" in the hero, the Introduction line, the lead of the four-color ribbon.
- **Logo Lagoon** (public-lagoon): the second chevron and ribbon band; the Transparency line.
- **Logo Leaf** (public-leaf): the third chevron and ribbon band; the Advocacies line; the front hill and palm fronds of the countryside; the live dot.
- **Logo Gold** (public-gold): the fourth chevron and ribbon band; the Events line (with Night text on its fills); the focus ring on form fields; the closing-band button. Never text.

### Public Site: Text-Safe Steps
Deeper steps of the same hues, at 4.5:1 or better on white and on the pastels. Whenever an official color carries type, the step carries it instead.
- **Text Violet** (public-text-violet): the tagline, the About destination banner fill, the home primary button, the Introduction nav label, the "C" letters of "Candelaria".
- **Text Lagoon** (public-text-lagoon): Transparency's nav label, page head fill and buttons.
- **Text Leaf** (public-text-leaf): Advocacies' nav label, page fills and buttons.
- **Text Gold** (public-text-gold): Events' nav label and the Events destination title.
- **Text Pink** (public-text-pink): one of the five letter colors in "Candelaria"; used nowhere else.
- **Display Cyan** (public-display-cyan): large display type only (24px bold and up, 3:1 on the pastel sky): "Natin!" and the cyan letters of "Candelaria", so the logo's cyan stays cyan at hero size. Never body, UI or small type; those use Text Lagoon.

### Public Site: Line Colors
Each inner page sets one line, a deep step and a pale tint: Introduction violet (deep #4f3d96, tint #efebfa), Constitution **Indigo** (public-indigo; deep #2a1d66, tint #ebe8f6), Best practices **Teal** (public-teal; deep #075665, tint #e3f2f4), Roster **Forest** (public-forest; deep #1f4f1d, tint #e6f0e4), Advocacies leaf (deep #3f7629, tint #ebf4e5), Events gold (deep #7a6000, tint #fbf4d6), Transparency lagoon (deep #0d6f80, tint #e2f4f7), Contact **Night** ink (tint #ecedf1). Indigo also serves as the hover for the home primary button and the About banner.

### Public Site: Field and Neutrals
- **Pastel field**: Violet (#dccfff), Pink (#ffd2ef), Lagoon (#c4f1f4), Mint (#d4f6d6), Butter (#fff3b8) as soft radial washes on a **Sky** base (public-sky, #f8f6ff; page heads use #faf8ff), under a white grid line at rgba(255, 255, 255, 0.78).
- **Night** (public-night): all public body text, headings, the footer and closing band, the Contact button. The public world's ink; never pure black for text.
- **Ink 2** (public-ink-2): secondary text, leads, labels.
- **Platform** (#ffffff) and **Platform 2** (#f4f4f7): page and quiet hover fills, bar tracks.
- **Rules**: rgba(27, 29, 41, 0.12) hairline and rgba(27, 29, 41, 0.22) strong rule for tables and lists.
- **Negative money**: #b23a48.

### Named Rules
**The Official Four Rule.** Purple, cyan, green and yellow are the organization's official colors. Keep them; don't introduce a new hue for decoration. New states use the existing washes and inks.

**The Wash-Not-Fill Rule.** Status and secondary emphasis use a pale wash with a deep ink of the same hue (for example #315c37 on #e7f2e2). Saturated fills are reserved for the primary action and the brand gradient.

**The Text-Safe Step Rule (public).** The official four are for shapes: chevrons, ribbons, fills, markers. Type in color always uses its text-safe step (#6650a8, #0e7c8f, #3d7a29, #8a6d00, #b8397a) or the page's line where it already clears 4.5:1. The single exception is Display Cyan (#1897ab), allowed only on display type 24px bold and larger.

**The One Line Rule (public).** An inner page wears exactly one line color, set once on the body, and every colored element on the page (head wash, chevrons, section markers, section tabs, numbered stops, primary button, tags, table hover) reads from it. Home alone uses all four.

## Typography

**Display Font (portal):** Segoe UI (with Aptos, Arial, Helvetica, sans-serif)
**Body Font (portal):** the same stack
**Label/Mono Font (portal):** the same stack; figures use tabular numerals

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

### Public Site
**Display Font:** Nunito (variable 600–1000, with Segoe UI, sans-serif)
**Body Font:** Figtree (400–800 with italics, with Segoe UI, Arial, sans-serif)
Both load from Google Fonts in `public_base.html`. Sizes come from `--t-*` variables in `public.css`.

**Character:** Nunito's rounded terminals carry the logo's chunky "KN" into every heading; Figtree is a clean, friendly grotesque that keeps reading pages professional.

- **Hero name** (Nunito 1000, clamp(58px, 15vw, 108px), 0.95, -0.035em): "Kaya" in Logo Violet and "Natin!" in Display Cyan. Under it "YOUTH" (Nunito 800, clamp(26px, 6.4vw, 48px), 0.28em tracking, capitals, #3d4150) and "Candelaria" (Nunito 900 italic, clamp(32px, 8vw, 46px)) with each letter cycling through the text-safe steps (Display Cyan for its cyan letters). Home only.
- **Page title** (Nunito 900, clamp(38px, 5.6vw, 76px), 0.98, -0.02em, max 16ch): inner page h1 in Night.
- **Section** (Nunito 800, clamp(26px, 3vw, 38px), 1.08): h2.
- **Title** (Nunito 750, 20px, 1.25): h3, person names, table row heads.
- **Tagline** (Nunito 800, clamp(18px, 2.2vw, 24px), Text Violet): "Basta't sama-sama, Kaya Natin!" under the hero name.
- **Lead** (Figtree 400, 19px, 1.55, max 58ch): page head intro.
- **Body** (Figtree 400, 17px, 16px under 560px, 1.6, measure 66ch).
- **UI** (Figtree 800, 15px): buttons, nav labels, destination actions.
- **Meta** (Figtree 700, 14px): section tabs, breadcrumb, notes.
- **Label** (Figtree 800, 12px, 0.1–0.12em, capitals): table column heads, figure labels, contact field names. Labels name data; they never sit above a heading.
- **Figures** (Nunito 900, clamp(22px, 2.4vw, 32px), tabular numerals): transparency totals.

### Named Rules
**The Numbers Line Up Rule.** Money and counts always use tabular numerals, right-aligned in tables, with ₱ and two decimals.

**The Clear Step Rule.** Adjacent heading roles differ by at least one clear step (42 → 22 → 18 → 16). Headings wrap balanced, paragraphs wrap pretty; never add a new size without adding it to the ramp.

**The Rounded Not Scripted Rule (public).** Personality comes from Nunito's weight and the per-letter color, never from a hand-script face. "Candelaria" stays italic Nunito Black.

## Layout

**Portal (Operate).** A fixed 256px sidebar on the left (Sidebar White, hairline right edge) and a content column up to 1180px wide beside it, with 32px top padding. The sidebar groups every destination by job: Overview; Finances; People; Communication; Records. The current page is a lavender pill. The signed-in person and Password / Log out sit at the bottom. Below 960px the sidebar becomes an off-canvas drawer opened from a sticky top bar with a menu button; a dimmed scrim closes it, as does Escape.

Every portal page uses the same skeleton: an optional back link (only on true sub-pages, e.g. a ledger back to Finance overview), the page header (title and one-line purpose on the left, stat tiles on the right, the most important tile tinted lavender), flash messages, then white **panels**. The Overview page is a two-column grid (attention, activity and totals on the left; coming up and shortcuts on the right) that stacks below 1100px. Stat tiles become a two-column grid on phones.

Portal spacing runs on a 4px base: 4, 8, 12, 16, 24, 32, 48, 72, 104px (`--space-*`).

**Public site (Persuade / Read).** A sticky white header (97% white, 10px backdrop blur, hairline bottom) topped by a 6px four-color ribbon, over a 1200px centered column with a 24px gutter (16px under 560px). The home hero fills the first viewport (100svh less the header) and centers the chevrons, name, tagline and two actions, with the countryside pinned along its bottom edge (1600 × 580 aspect, at least 260px tall). Under 700px the hero is no longer full-height, and the scene keeps at least 250px with its own phone palm set. Below it, the destinations stack in a single 980px column on a pale green-to-white fade.

Inner pages open with the holographic page head (at least 440px tall; breadcrumb, logo mark, title and lead on the left over a pale wash, the page scene full-bleed behind them; at 860px and below the scene becomes a 250px band along the bottom), then the section tabs, then full-width sections 72px apart (48px under 860px) separated by hairlines, alternating white and the page's tint. Long documents (Introduction, Constitution) read in one 860px column; the section tabs are their contents. Two-column splits, feature cards, numbered lists and the contact grid collapse to one column under 860px; the nav becomes a menu button under 960px.

Public spacing runs on `--s1`–`--s9`: 4, 8, 12, 16, 24, 32, 48, 72, 112px.

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

### Public Site
Depth on the public site is mostly light, not shadow: layered pastel washes, the white grid fading out toward the countryside, and the countryside's stacked hills. Shadows are few and violet-tinted.
- **Panel** (`box-shadow: 0 14px 34px rgba(117, 98, 181, 0.08)`): resting panels.
- **Home primary** (`box-shadow: 0 10px 24px rgba(117, 98, 181, 0.35)`): the "Get to know us" button on the pastel hero.
- **Destination hover** (`box-shadow: 0 14px 30px` the banner's color at 18%): banners on hover, with an 8px slide right.
- **Dropdown** (`box-shadow: 0 22px 50px rgba(27, 29, 41, 0.16)`): the About menu.
- **Header logo** (`box-shadow: 0 4px 12px rgba(117, 98, 181, 0.25)`).
- **Logo mark** (`filter: drop-shadow(0 4px 10px rgba(117, 98, 181, 0.25))`): the mark in inner page heads.
The header and section tabs use no shadow, only a hairline and blur.

### Named Rules
**The Gentle Lift Rule.** Only things you can click lift on hover (1px for buttons, 2px for cards). Static content never moves.

## Shapes

**Portal.** Consistently rounded, never sharp, never blobby: 8px on controls (buttons, inputs, nav links, menus), 12px on portal cards, 16px on dialogs, full pills for statuses and counts. Borders are 1px hairlines in slate at 8–10% opacity. The brand mark is a 46px rounded square (12px) filled with the purple-to-cyan-to-green gradient.

**Public site.** Rounder and bolder. Buttons, nav links, tags and the menu toggle are full pills or circles. Containers step from 12px (fields, flash messages, event dates) to 16px (dropdown), 18px (destination chevron tiles), 20px (report frame, empty state), 24px (panels, feature cards) and 28px (destination banners; 22px on phones). Borders are 2px soft rules (rgba(27, 29, 41, 0.12)); destination banners use a 3px border of their color at 35%. Circles mark numbered stops (56px) and person photos (with an 8px tint halo); section markers are drawn chevrons (20 × 26px). The recurring silhouette is the forward chevron, `polygon(0 0, 55% 0, 100% 50%, 55% 100%, 0 100%, 45% 50%)`; buttons and links end in a drawn arrowhead (an 8px rotated corner of 2.5px strokes).

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
- **Corner Style:** 12px.
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

### Panels
The portal's standard container: white, 1px hairline, 12px corners, a barely-there shadow (0 1px 2px), 24px padding, and a header row (Section-size title on the left, one secondary action on the right). Tables inside a panel run edge to edge. Panels never lift on hover.

### Attention List (signature, portal Overview)
Rows on a pale lavender-gray tint, each with a 34px tinted icon square (amber for things to act on, lagoon for information), one plain sentence, and one small secondary button naming the action ("Review", "Add emails"). When nothing needs attention it says "All clear" in success green.

### Ledger Table (signature)
The portal's main workhorse: a white card with a toolbar, then a full-width table whose header row is lavender with purple-deep, letter-spaced column titles. Every column title is a button with a ▾ that opens a sort-and-filter menu. Money columns are right-aligned tabular figures, empty cells show a pale "—", and row actions (Edit, Delete) sit right-aligned as link buttons. A stat strip in the page header (uppercase labels over 24px Figure numbers) updates live as filters change.

### Dialogs
Centered modal cards (16px radius, up to 680px wide, 480px for confirmations) with a header row (Section-size purple-deep title and a round × close button), a scrolling body and a footer with Cancel and the main action. All add, edit, delete and confirm flows use dialogs, not inline forms.

### Public Buttons
Pills that point forward.
- **Shape:** full pill, at least 50px tall, 12px 22px padding, Figtree 800 15px, a 2px border, and a drawn arrowhead after the label.
- **Primary:** filled with the page's line (its text-safe head where one exists) and white text (Night on gold); hover fills the line's deep step. On home it is Text Violet with the violet glow, hovering to Indigo.
- **Ghost / Secondary:** transparent (75% white on the hero) with a 2px Night border; hover fills Night with white text.
- **Hover:** a 2px lift (0.2s, ease-out). **Focus:** a 3px Night outline, 3px offset, with a white separating ring, on every focusable element.
- **Text link:** Night 800 text over a 3px line-colored underline bar, with an arrowhead that slides 3px on hover.

### Public Navigation
- **Header:** the logo image (46px, 12px corners) and "Kaya Natin! Youth" in Nunito 900 with "CANDELARIA" in small spaced capitals below. Then Home, About (a dropdown for Introduction, Constitution & By-Laws, Best practices, Roster), Advocacies, Events, Transparency, and a Night "Contact us" pill that hovers to Indigo.
- **Label colors:** each nav label is set in its page's text color (Introduction and About Text Violet, Constitution Indigo, Best practices Teal, Roster Forest, Advocacies Text Leaf, Events Text Gold, Transparency Text Lagoon); "Home" spells its four letters in the four text-safe steps. No dots. Hover is a 9% wash of the label color; the current page adds a 12% wash and a 2px border at 45%.
- **Phones (under 960px):** a 46px circular menu button with a drawn three-line icon reveals the same links, About grouped under a small capitals label, and a full-width Contact button.

### Chevron (signature, public)
The logo's forward chevron, drawn with a clip-path, never typed. On home, four 28px chevrons (24px on phones) in violet, lagoon, leaf and gold slide in from the left with a 0.1s stagger. Inner page heads carry the logo's own mark instead (`_logo_mark.html`, 112px wide): a dot and three rounded chevrons with white rims and gradient fills (violet to lagoon, lagoon to mint, leaf to butter), from the organization's cover banner, stepping in with a 0.08s stagger. Inside destination banners, one 26 × 30px chevron in a tinted 56px rounded tile, sliding 5px right on hover.

### Home Hero (signature, public)
Centered on the pastel field: chevrons, the two-color "Kaya Natin!", spaced "YOUTH", per-letter "Candelaria" (letters settle in with a 0.05s stagger), the tagline, then "Get to know us" (About) and the ghost "Our advocacies". The whole name floats 10px on a 6s loop after the entrance.

### Countryside (signature, public)
Pixel art in the idiom of the organization's posters, not smooth vector. An inline SVG partial (`public_site/templates/_countryside.html`) at the foot of the home hero, rendered with `shape-rendering: crispEdges` so every hill step and frond is a hard-edged block on a pixel grid. Layered stepped hills in the leaf greens and pale rice-field rows, a glowing sun (7s scale-and-fade), and coconut palms drawn as varied pixel sprites (no two identical) that sway ±1.2° on offset 6s loops. Wide screens show one palm set (`palm-wide`); phones swap in their own set (`palm-phone`) in a taller scene. The pixel scene sits against the smooth pastel light; that contrast is the point. No outlines, no dithering textures, no photography, no anti-aliased curves.

### Destination Banner (signature, public home)
Stacked, full-width poster rows in a 980px column: chevron tile, a Nunito 900 title in the destination's text color over a one-line description, and an action word with an arrowhead ("Start here", "Explore", "See what's on", "See our finances"). White with a 3px border at 35% of the color; hover slides 8px right, firms the border and adds a tinted shadow. **About** is the filled primary: Text Violet fill, white type, a larger title, hovering to Indigo.

### Holographic Page Head (signature, public)
Every inner page opens in its own color as light: two radial washes of the line (32% and 22%) with pastel lagoon and pink, on #faf8ff, under a 40px white grid. Night breadcrumb (joined by short bars), the logo mark, the page title and an Ink 2 lead, held legible by a pale wash (#faf8ff at 94% fading to clear by 56% across, or top-down on phones) over the page scene (see Page Scene).

### Page Scene (signature, public)
Each inner page head is a moving background, not a picture beside the title: a generated, full-bleed pixel-art SVG (`public_site/templates/_art_<page>.html`, class `page-scene`) on a 260 × 72-cell grid, anchored bottom right (`xMaxYMax slice`) and drawn with `shape-rendering: crispEdges`, people included, in the idiom of the organization's posters and cover banner. Most pages stand in a Candelaria town backdrop: rows of pastel houses, a sari-sari-style shop, mid-rise buildings, street lamps and an asphalt street; a jeepney drives across Introduction and Contact. Each page then shows its subject: Introduction, the rural edge of town (palms, bahay kubo, a farmer in a salakot, a carabao, rice rows); Constitution, a civic hall with columns, scales of justice, the Philippine sun and stars, an open book on a lectern, a gavel; Best practices, a checklist, lightbulb, medal and teammates; Roster, members standing together; Advocacies, young advocates with a megaphone, heart-and-leaf placards, a sapling and a raised arm; Events, banderitas, a calendar, a stage with a microphone, a crowd; Transparency, a bar chart, coin stacks, a peso coin, a magnifier; Contact, envelopes, a phone, speech bubbles, a map pin.

**Motion vocabulary.** travel (the jeepney and clouds cross the scene), fly (envelopes on an arc), sway and sway-top (palms, banderitas, ±1°), tilt (the scales, ±3°), spin (the Philippine sun, 40s), twinkle (stars), glow, bob, rise (coins, check badges), fall (confetti), pop (speech bubbles), flip (the peso coin), sweep (the magnifier), and a one-time grow (bars). People move only in small whole-pixel steps: idle (a 1-cell bob on a stepped 2s beat, timed per person), hop (performers, stepped 0, -2, -3, -1 cells over 1.1s), waving (two arm frames swapped on a 0.8s step), and audience heads bobbing. No one walks. Under reduced motion everything stops. The scene is decoration (`aria-hidden`).

**The Small Pixel People Rule (public).** People are small pixel-art sprites, about 23 cells tall in the 72-row scene, with crisp edges and the same 1px dark outline as the rest of the scenery. They wear varied everyday clothes (tees, hoodies with pocket and strings, jackets over tees, striped shirts, polos, dresses, long sleeves; jeans, cargo pants, shorts, skirts; caps and totes), with Filipino skin tones and varied hair (short, long, bob, bun, ponytail, curly, spiky). Props are held, not floating: megaphone, a placard with heart and leaf icons, a seedling pot, a phone, a tote. A farmer in a salakot belongs on Introduction. Motion is idle only (bob, hop, a two-frame wave), in whole-pixel steps. No walk cycles, no uniforms as a rule, no mascots.

**The Picture-Not-Words Rule (public).** Page scenes are pixel art, people included, in the posters' idiom, picturing the page's subject. They never contain words or numbers, and never invent facts (no fake figures, no real people's likenesses, no events that did not happen).

### Time of Day (signature, public home)
The home hero follows the visitor's clock. A small inline script sets `data-daypart` on the root element: morning (5:00–9:30), day (9:30–16:00), sunset (16:00–18:45) and night (the rest), checking again every 10 minutes; `?sky=morning|day|sunset|night` previews each one.
- **Morning:** peach light low on the left (#ffe3c2 over the pastels on #fbf7ff), a low golden sun (#ffd27a) left of centre, a faint peach veil (#ffb27a at 8%) over the fields.
- **Day:** the standard pastel field and sun.
- **Sunset:** a lavender-to-pink-to-orange sky (#efe4ff, #ffe6ee, #ffe0c4 with #ffc58f and #ffc2d6 glows), an orange sun (#ff9a5c) sinking right, a warm veil (#ff6f61 at 14%) over the fields.
- **Night:** a deep violet sky (#17143a to #3a2f73), the grid nearly gone (6% white), a pixel crescent moon and twinkling stars (stars hidden on phones), the fields under a dark veil at 50%. The hero type switches to light steps: "Kaya" #b9a8ff, "Natin!" #6fe0f0, "YOUTH" #f4f2ff, "Candelaria" letters #c6b6ff, #7fe3f2, #a6e483, #ffe27a and #ff9cc9, the tagline #e3dcff. The ghost button turns light-on-dark (#f4f2ff text and border on 8% white).

### Section Tabs (signature, public)
"On this page" for inner pages. Built by `public.js` from the page's section headings (two or more) and pinned under the header (97% white, 10px blur, hairline bottom). A Nunito 800 14px "On this page" label (hidden at 560px and below), then a sideways-scrolling row of pill tabs: white, 2px border at 30% of the line, Figtree 700 14px Night labels, each led by a small drawn chevron (9 × 11px) in the line color. Hover tints the tab with the line's tint and firms the border. The tab for the section in view fills with the line's head color and its text color for the line (white, Night on gold), with a matching chevron, and scrolls into view on narrow screens.

### Public Containers
- **Panel:** white, 2px soft rule, 24px corners, the violet panel shadow, 32px padding.
- **Section marker:** each section heading starts with a drawn chevron (20 × 26px; 16 × 21px on phones) in the page's line head color.
- **Numbered stops:** 56px line-filled circles in Nunito 900 joined by a 14px line track at 20%.
- **Timetable lists** (events, tables, figures, contact details): a 3px Night top rule, strong-rule row dividers, small capitals column labels, and the line's tint on row hover. Event dates sit in line-filled 12px-rounded blocks.
- **Empty state:** a 2px dashed rule, 20px corners, centered Night title and Ink 2 note.

### Public Fields
White, 2px strong rule, 12px corners, at least 50px tall, 800-weight labels above. Focus turns the border Night and adds a 4px Logo Gold ring.

### Public Footer
A Night band under the 6px four-color ribbon (hard stops, a quarter each): organization name and description, Explore and Contact link lists in 80–88% white, and a bottom row with the year and the Officers' portal link. The closing call-to-action band uses the same Night and ribbon with a gold button.

### Motion (public)
Entrances use `cubic-bezier(0.16, 1, 0.3, 1)` (0.7–0.9s); loops are slow (float 6s, palm sway 6s, sun 7s, live dot 2.4s); hovers are 0.2–0.25s. Under `prefers-reduced-motion` every CSS animation and transition is off and the countryside's SVG animations are paused at their first frame.

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
- **Do** give every new public inner page one line color on its body class and build it from the holographic page head with its logo mark and moving page scene, the section tabs and chevron section heads.
- **Do** set colored public type in the text-safe steps (#6650a8, #0e7c8f, #3d7a29, #8a6d00, #b8397a) and keep the official four for chevrons, ribbons and fills.
- **Do** draw every chevron and arrowhead in CSS or SVG.
- **Do** keep public containers at 20–28px corners with soft 2px rules, and buttons as pills.
- **Do** make every public loop slow and stop it under reduced motion, SVG animations included.

### Don't:
- **Don't** add hues outside the official four plus the neutral and status palette.
- **Don't** use pure black text or pure gray borders; use Ink Slate and the slate hairline.
- **Don't** set yellow (#d8cf65) as text or as a large fill; it is a highlight only.
- **Don't** make static content move on hover; only clickable elements lift.
- **Don't** go back to inline expand-to-edit forms in tables; use the dialog pattern.
- **Don't** put a colored bar along one edge of a rounded card, or a small uppercase label above a heading.
- **Don't** give each public page its own inline stylesheet; everything public lives in `public_site/static/css/public.css`.
- **Don't** use Logo Gold (#e7bf1e) or Logo Leaf (#5a9e3c) as text on white or the pastels.
- **Don't** give one public page two line colors, or reuse the portal's Segoe UI ramp, gradient buttons or lavender pills on the public site.
- **Don't** type chevrons, arrows or icons as glyphs or emoji.
- **Don't** set "Candelaria" or any public heading in a script face, and don't add mascots or cartoon type.
- **Don't** redraw the countryside as smooth vector curves or replace it with stock photography; keep it crisp-edged pixel art on one grid.
- **Don't** use Display Cyan (#1897ab) below 24px bold.
- **Don't** put words, numbers or invented facts in page scenes, or draw them as smooth vector or clip art.
- **Don't** put a static picture box beside a page title; page illustration is the moving background scene behind the head.
- **Don't** draw people as smooth vector figures, as mascots, larger than the scenery's scale, or without Filipino skin tones.
- **Don't** give people walk cycles or travel; their motion stays idle (bob, hop, two-frame wave) in whole-pixel steps.
- **Don't** bring back a station-line or progress-rail navigation for page sections; sections are reached through the pill tabs.
