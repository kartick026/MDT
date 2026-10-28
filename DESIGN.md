---
name: MDT
description: A tactile working surface for evidence-based architecture review.
colors:
  bg-base: "#e8edf1"
  bg-surface: "#e8edf1"
  bg-card: "#e8edf1"
  bg-card2: "#e2e9ee"
  bg-input: "#e8edf1"
  text: "#243742"
  text-dim: "#50616e"
  text-faint: "#586875"
  border: "#cbd5dd"
  border-md: "#bdcad4"
  border-hi: "#8ba2b3"
  blue: "#24618b"
  cyan: "#176b68"
  purple: "#65549a"
  green: "#236848"
  yellow: "#815a10"
  orange: "#9b4b19"
  red: "#ac3449"
  blue-dim: "#dce7f1"
  cyan-dim: "#d6e7e5"
  purple-dim: "#e4dff0"
  green-dim: "#dbe9df"
  yellow-dim: "#eee5cc"
  red-dim: "#f1dce0"
  white: "#ffffff"
  primary-hover: "#105b58"
typography:
  headline:
    fontFamily: "Inter, sans-serif"
    fontSize: "clamp(26px, 2.6vw, 36px)"
    fontWeight: 700
    lineHeight: 1.22
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Inter, sans-serif"
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontFamily: "Inter, sans-serif"
    fontSize: "12px"
    fontWeight: 650
    lineHeight: 1.5
  evidence:
    fontFamily: "JetBrains Mono, monospace"
rounded:
  radius: "16px"
  radius-lg: "24px"
  radius-sm: "10px"
  button: "11px"
  navigation: "13px"
  finding: "12px"
  chip: "8px"
spacing:
  compact: "8px"
  control-gap: "9px"
  small: "12px"
  regular: "18px"
  roomy: "22px"
  section: "30px"
components:
  button-primary:
    backgroundColor: "{colors.cyan}"
    textColor: "{colors.white}"
    rounded: "{rounded.button}"
    padding: "11px 17px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.white}"
  button-secondary:
    backgroundColor: "{colors.bg-base}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "11px 17px"
  input:
    backgroundColor: "{colors.bg-input}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius-sm}"
    padding: "11px 13px"
  nav-selected:
    backgroundColor: "{colors.bg-base}"
    textColor: "{colors.cyan}"
    rounded: "{rounded.navigation}"
    padding: "14px 17px"
  chip-info:
    backgroundColor: "{colors.blue-dim}"
    textColor: "{colors.blue}"
    padding: "4px 9px"
  card:
    backgroundColor: "{colors.bg-card}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius-lg}"
---

# Design System: MDT

## Overview

**Creative North Star: "The Soft Working Surface"**

Cool pearl-gray material, paired white and slate shadows, and deep teal actions make architecture review feel tactile and calm. Dark slate text and visible borders keep the soft material readable.

Depth belongs to surfaces and controls. Dense findings, history, scores, and modeled outcomes use flatter divisions so the evidence stays inspectable. The MDT identity and academic-alpha disclosure remain part of the product.

**Key Characteristics:**
- Pearl-gray working ground with dark slate ink.
- Raised actions and inset fields or selected navigation.
- Flat, compact evidence inside spacious task surfaces.

## Colors

A cool pearl neutral system supports deep teal actions and restrained semantic colors. Token names retain the implemented CSS vocabulary; cyan names now resolve to deep teal.

### Primary

- **Deep Teal** (`cyan`): primary actions, current navigation, focus outlines, graph relations, and text selection. The hover variant deepens filled actions.

### Secondary

- **Working Blue** (`blue`): repository entry and information badges.
- **Muted Violet** (`purple`): existing category accents where used.
- **Evidence states:** green means low risk or success; amber means medium risk or warning; orange means high risk; red means critical risk or error. Their pale dim companions group corresponding badges. Unknown graph risk uses faint slate.

### Neutral

- **Pearl Gray** (`bg-base`, `bg-surface`, `bg-card`, `bg-input`): shared material across canvas and controls.
- **Recessed Pearl** (`bg-card2`): graph viewport and secondary planes.
- **Slate Ink** (`text`), **Secondary Slate** (`text-dim`), and **Faint Slate** (`text-faint`): reading hierarchy, captions, and placeholders.
- **Soft / Medium / Strong Edge** (`border`, `border-md`, `border-hi`): separators and interactive boundaries.

## Typography

**Headline and Body Font:** Inter, sans-serif. The shipped display alias resolves to the same family; there is no separate decorative display face. **Evidence Font:** JetBrains Mono, monospace, retained for code and graph labels.

### Hierarchy

- **Headline:** the fluid headline token carries page titles; the demo title uses a related fluid size (25–37px), and becomes 32px at the narrowest breakpoint.
- **Title:** the title token carries workspace section headings. Smaller guide headings use 19px.
- **Body:** the body token is the page baseline. Supporting paragraphs commonly use 12–13px; demo text is limited to 44ch.
- **Label:** the label token carries buttons; navigation uses 14px at desktop and 12px on mobile. Metadata and badge text use 10–11px.
- **Numeric evidence:** scores use Inter (32px, 650) and tabular numerals; history cells also use tabular numerals.

## Layout

Desktop uses a sticky full-height rail (224px) and a fluid content column capped at 1456px. Workspace padding is 48px vertically at the top and clamp(24px, 3.5vw, 64px) horizontally; the workspace has a 30px section gap. Cards use clamp(22px, 2.4vw, 34px) padding. The welcome directory uses a broad demo panel beside a narrower repository panel. In the signed-in project grid, the featured demo spans every column; regular project cards have a 240px minimum height and stretch equally within each row. The featured panel uses an internal two-column grid and a named inline-size container (`demo-card`). Its walkthrough hides when the actual card content width is 600px or less, and the copy spans both columns.

At 1250px the welcome directory proportions tighten. At 1050px summary scores stack. At 950px the rail narrows to 190px, welcome cards stack, and guide links become rows. At 720px the rail becomes a static compact top header with horizontal navigation, workspace padding becomes 30px 22px, and project tabs fill the width. At 520px dense panels tighten to 22px 18px. At 1600px and above content gains 60px top padding. Existing evidence grids may have additional local responsive rules.

## Elevation & Depth

Paired opposing soft shadows describe one continuous material. Borders and dark ink supplement depth. Dialogs alone use a broad overlay shadow and tinted backdrop.

### Shadow Vocabulary

- **Raised surface:** `8px 8px 18px #c9d1d9, -8px -8px 18px #ffffff`; main cards.
- **Raised control:** `4px 4px 9px #c7d0d8, -4px -4px 9px #ffffff`; neutral buttons, brand mark, demo shortcut.
- **Inset:** `inset 4px 4px 8px #cbd4dc, inset -4px -4px 8px #ffffff`; inputs, current navigation, pressed controls, graph viewport.
- **Primary action:** `4px 4px 10px #b4c6ca, -4px -4px 10px #fff`; filled teal actions. Hover switches to teal inset shading.
- **Dialog:** `12px 18px 60px #50616e55`; modal elevation, with `#24374270` backdrop.

**The Pressed Selection Rule.** Selected navigation presses inward; available secondary actions remain raised.

**The Evidence Plane Rule.** Use borders and tonal grouping inside evidence; avoid stacking raised cards inside raised cards.

Controls transition shadow, background, and color over 180ms ease-out without hover translation. The reduced-motion query removes animations and transitions and resets smooth scrolling across elements and pseudo-elements.

## Shapes

Broad cards use the large radius; inputs use the small radius; buttons use their dedicated rounded corner. Finding and preview panels use the finding radius. Navigation links are gently rounded and the session avatar is circular. Fine borders preserve boundaries against the shared ground. Outline Lucide SVG icons use a 1.8 stroke width and do not shrink in flex layouts.

## Components

### Buttons

Tactile and deliberate. Neutral controls use the small raised shadow; primary controls use deep teal with white text. Standard buttons are at least 44px high. Neutral hover and active states press inward. Disabled buttons use opacity .6 and remove shadows; copying and quick-preset chips are denser (34px minimum), with outlined treatment rather than elevation.

### Chips

Compact evidence markers use 10px text, weight 650, and 4px 9px padding. Information, success, warning, and danger variants pair dark semantic ink with pale semantic grounds and visible borders.

### Cards / Containers

Large rounded panels establish task regions. Internal finding rows use pale flat grounds and thin borders. Expanded findings do not gain another raised shadow. Score bands use shared top and bottom rules and vertical separators on wide screens; separators become horizontal when stacked.

### Inputs / Fields

Recessed controls have a visible edge, 44px minimum height, 13px text, and the input token padding. Focus on standard fields uses a teal 2px outline with 2px offset. Global focus-visible uses a teal 3px outline with 4px offset. Placeholders remain fully opaque in faint slate; errors use red text and a pale error region.

Native selects and the project switcher share `appearance: none`, a 16px SVG chevron positioned 14px from the right edge, a 40px arrow gutter, `min-width: 0`, `max-width: 100%`, and 44px minimum height. Options use slate text on the pearl-gray ground. The project switcher width is `min(320px, 100%)`. Forced-colors mode restores native appearance, removes the decorative chevron, and resets the end padding to 13px. History and findings selects carry explicit accessible labels; graph selects use the shared padding instead of inline padding overrides.

### Navigation

Primary navigation uses outline icons, labels, and aria-current selection. Both primary links and project tabs use inset selected surfaces. The project tab tray is itself recessed and scroll-safe through its existing responsive layout. Small screens use the horizontal top navigation and retain access to Projects, History, Account, and the demo shortcut.

### Evidence and dependency graph

Findings, remediation previews, history, and code remain dense, bordered working data. Search is inset; selected findings subtabs use a pale teal ground. The graph sits in a recessed viewport with a flat relation inspector. Graph relations use teal, broken relations use red, and risk nodes follow the low/medium/high/critical palette. Selected or hovered relations thicken from 1.8px (2.4px broken) to 2.8px. Edges expose keyboard focus and Enter/Space inspection, with relation descriptions in accessible labels. Do not use color alone to convey relation or risk meaning.

No new raster assets are shipped by this visual system. Source SVG icons and graph geometry provide the visual marks.

## Do's and Don'ts

### Do:

- **Do** pair semantic colors with readable labels, icons, or values.
- **Do** retain visible keyboard focus and honor reduced motion.
- **Do** use outline SVG icons and preserve clear evidence disclosures.

### Don't:

- **Don't** use elevation as the sole indication of selection or interaction.
- **Don't** turn inline legacy cyan-alpha remnants into new palette tokens.
- **Don't** apply raised shadows to every table row, finding, or score.

Not canonized: legacy inline cyan-alpha graph accents remain local implementation drift. Tiny dense graph labels are evidence-specific exceptions, not a general text scale. They are recorded without changing the frontend during this documentation pass.
