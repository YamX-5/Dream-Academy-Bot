---
name: Dream Academy
description: The academy's books kept like an official basketball scoresheet on platinum stock.
colors:
  paper: "#EEF0F3"
  sheet: "#FAFBFC"
  sheet-2: "#F4F5F7"
  sheet-3: "#E8EBEF"
  rule: "#D6DAE1"
  rule-soft: "#E4E7EC"
  rule-strong: "#B0B6C0"
  ink: "#14161B"
  ink-2: "#4A4B50"
  muted: "#626873"
  faint: "#707680"
  baby-blue: "#6EA3EE"
  baby-blue-text: "#2660BA"
  ok: "#18804E"
  warn: "#A8680E"
  bad: "#BE322A"
  whatsapp: "#168C46"
  statement-charcoal: "#1C1D21"
  statement-ink: "#EEF0F3"
typography:
  display:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum, lnum"
  headline:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.01em"
    fontFeature: "tnum, lnum"
  section:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 800
    letterSpacing: "0.12em"
  body:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 500
    lineHeight: 1.45
  body-arabic:
    fontFamily: "Tajawal, Montserrat, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 500
    lineHeight: 1.45
  sub:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
  label:
    fontFamily: "Montserrat, Tajawal, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.09em"
rounded:
  hair: "1px"
  sm: "2px"
  md: "3px"
  lg: "4px"
  statement: "6px"
  sheet-top: "10px"
  member: "12px"
spacing:
  tight: "6px"
  gap: "10px"
  row-y: "11px"
  gutter: "16px"
  stack: "16px"
  stack-lg: "20px"
  page-lg: "40px"
components:
  button-ink:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "42px"
  button-ink-hover:
    backgroundColor: "{colors.ink-2}"
  button-line:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "42px"
  button-quiet:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    height: "42px"
  button-quiet-hover:
    backgroundColor: "{colors.sheet-2}"
  button-danger:
    textColor: "{colors.bad}"
    rounded: "{rounded.md}"
    height: "42px"
  button-whatsapp:
    backgroundColor: "{colors.whatsapp}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
  button-sm:
    height: "34px"
    padding: "0 12px"
  button-xs:
    height: "28px"
    padding: "0 9px"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "44px"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.lg}"
  sheet-row:
    padding: "11px 16px"
    height: "52px"
  tab:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "34px"
  tab-on:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
  tag:
    rounded: "{rounded.sm}"
    padding: "4px 7px"
    typography: "{typography.label}"
  monogram:
    backgroundColor: "{colors.sheet-3}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    size: "36px"
  statement:
    backgroundColor: "{colors.statement-charcoal}"
    textColor: "{colors.statement-ink}"
    rounded: "{rounded.statement}"
  member-card:
    textColor: "{colors.ink}"
    rounded: "{rounded.member}"
    padding: "20px 22px"
    width: "420px"
---

# Design System: Dream Academy

## Overview

**Creative North Star: "The Platinum Scoresheet"**

Every screen is a page of the academy's official book: graphite ink on cool platinum paper, ruled into boxes by 1px hairlines, with big tabular numerals where a scorer would write the score. Structure comes from rules, not from floating cards; a section is a ruled sheet with a header line, and its content is a stack of rows separated by softer rules. Each row ends in its action.

The feel is premium and restrained, after a charge-card statement rather than a SaaS dashboard. Two objects are allowed to be physical: the charcoal **statement** panel that heads the dashboard (the account summary) and the brushed-metal **member card** on a player's page. Everything else lies flat on the paper. The baby blue of the logo's D is the only accent and it marks state (the next session, the active nav item, focus, links), never decoration.

The system is bilingual by construction: Montserrat (the logo's face) carries Latin text and every numeral; Tajawal carries Arabic. Numerals are always isolated LTR and tabular, so money and counts line up in both directions. Light and dark themes share one token set of RGB triplets.

**Key Characteristics:**
- Hairline-ruled sheets, 1px rules, corners of 2 to 4px.
- Tabular Montserrat numerals as the loudest type on any screen.
- One accent (baby blue), used for state only.
- The 12-session package always drawn as a tally of boxes.
- Two lifted objects only: the statement panel and the member card.
- Full RTL with logical properties; uppercase tracking switches off in Arabic.

## Colors

Graphite and platinum neutrals carry almost everything; one baby-blue accent and three status inks do the signalling.

### Primary
- **Logo Baby Blue** (baby-blue): the D of the logo. Fills and lines for state: the next box in a tally, the active nav indicator bar, focus rings and the input focus glow, chart lines, selection. Never a large fill.
- **Scorer's Blue** (baby-blue-text): the accent darkened for text on paper (links, "see all", the add-player tile, caret, checkbox tint). In dark mode it lightens to #86B4F4.

### Neutral
- **Platinum Paper** (paper): page background; also the active row of the desktop rail.
- **Sheet White** (sheet): surface of every ruled sheet, input, tab and overlay panel.
- **Sheet Wash** (sheet-2): row hover, quiet-button hover, assistant reply bubble.
- **Sheet Shade** (sheet-3): monogram squares and empty bar tracks.
- **Hairline** (rule): sheet borders, header and footer rules, ledger column dividers.
- **Soft Hairline** (rule-soft): rules between rows inside a sheet.
- **Strong Hairline** (rule-strong): interactive outlines (inputs, line buttons, tabs, empty tally boxes, scrollbars).
- **Graphite Ink** (ink): body text, primary button fill, selected tab and segment fill, toast.
- **Logo Charcoal** (ink-2): the logo's A; section headings, filled tally boxes, progress bars, secondary text.
- **Muted Ink** (muted): labels, sub-lines, units, sheet-header meta.
- **Faint Ink** (faint): placeholders, separator dots, build stamp. Not for information a user must read.
- **Statement Charcoal** (statement-charcoal) with **Statement Ink** (statement-ink): the dashboard statement panel only; drawn as a 160deg gradient #2A2B30 to #17181B with a 2px baby-blue top rule.

### Status
- **Paid Green** (ok), **Renewal Amber** (warn), **Debt Red** (bad): text, tag outlines, tally overrides and attendance tile fills. On the charcoal statement they switch to #6FD69E, #F0B860, #FF8A7E, and accent text to #8DB8F3.
- **WhatsApp Green** (whatsapp): the WhatsApp action button only.

### Named Rules
**The One Accent Rule.** Baby blue appears only where something is next, active, focused or linked. If removing it would not lose information, it should not be there.

**The Triplet Rule.** Colors are defined once as RGB triplets on `:root` and `:root[data-theme="dark"]` and consumed as `rgb(var(--token) / alpha)`. New surfaces use the variables, never fresh hex.

## Typography

**Display Font:** Montserrat (with Tajawal, system-ui)
**Body Font:** Montserrat 500 for Latin; Tajawal for Arabic (16px)
**Label/Mono Font:** Montserrat with `tabular-nums lining-nums` for every number

**Character:** A bold geometric sans taken straight from the wordmark, used at heavy weights for headings and numerals and at 500 for running text. Tajawal keeps the same plain geometry in Arabic.

### Hierarchy
- **Display** (700, 34px, 40px from 1024px, line-height 1): ledger figures: cash in the box, amount owed, totals.
- **Headline** (800, 22px, 26px from 1024px, 1.15): one page title per screen.
- **Title** (700, 22px, 1.05): secondary figures, such as "month lands at".
- **Section** (800, 12px, 0.12em, uppercase, ink-2): the heading in each sheet header.
- **Body** (500, 15px, 1.45): rows and forms; row names are set at 700.
- **Sub** (500, 12.5px, muted): the second line of a row, sheet meta.
- **Label** (700, 11px, 0.09em, uppercase, muted): field labels, ledger keys, tags.

### Named Rules
**The Tabular Numeral Rule.** Every number (money, counts, dates, percentages) carries the numeral class: Montserrat, tabular, LTR-isolated, with "JD" set as a smaller muted unit after it.

**The Arabic Case Rule.** In RTL, section headings, labels, tabs and ledger keys drop uppercase and tracking and step up to 13px. Uppercase tracking is a Latin device only.

## Layout

Phone first, one column: a sticky translucent top bar (logo, wordmark, tool buttons), content at 16px gutters with a 760px cap, and a fixed bottom nav whose columns equal the role's destinations. Sections stack 16px apart (20px at 1024px+). From 1024px a 236px side rail replaces both bars, content gets 28px by 40px padding inside a 1120px wrap, and paired sheets sit side by side in two columns.

Inside a sheet the rhythm is fixed: header 11px by 16px (min 44px), rows 11px by 16px (min 52px; compact rows 44px), body 14px by 16px. Ledgers are equal grid columns divided by vertical hairlines, with 2 columns on the phone and 3 or 4 on desktop. A four-figure ledger wraps to 2 by 2 on the phone with a horizontal rule. Overlays are bottom sheets on the phone and centred dialogs from 640px. All direction-sensitive spacing uses logical properties (`margin-inline-start`, `inset-inline`, `border-inline-start`).

## Elevation & Depth

The paper is flat. Depth comes from tone (paper, sheet, wash, shade) and hairlines, not shadows. Only the two physical objects carry a shadow, and both are long, soft and pulled in so they ground the object rather than float it. Overlays use a scrim, not a shadow.

### Shadow Vocabulary
- **Statement drop** (`box-shadow: 0 22px 44px -30px rgba(12,14,20,.6)`): the charcoal statement panel only.
- **Card in hand** (`box-shadow: 0 18px 40px -26px rgba(10,14,22,.55), inset 0 1px 0 rgba(255,255,255,.35)`): the member card only.
- **Scrim** (`background: rgba(8,10,14,.5)`): behind bottom sheets and dialogs; .35 behind the assistant drawer.

### Named Rules
**The Flat Paper Rule.** A sheet never casts a shadow. If a surface needs separation, give it a hairline or a tone step.

## Shapes

Corners are nearly square: 2px for tags and segment items, 3px for buttons, inputs, tabs and monograms, 4px for sheets and tiles. Larger radii mark the physical objects (statement 6px, member card 12px on an ID-card 1.586 ratio) and overlay panels (10px top corners as a bottom sheet, 6px as a dialog). Tally boxes and bars use 1px, like printed boxes. Circles are reserved for status dots. Borders are 1px throughout; empty tally boxes are 1.5px (2px when large), like a pen outline.

## Components

### Buttons
Solid and quiet, sized for a thumb.
- **Shape:** near-square (3px), heights 42 / 34 / 28px; small sizes grow to 40 / 34px on coarse pointers.
- **Ink (primary):** graphite fill, sheet-white text, 700 at 14px; hover steps to charcoal; press nudges down 1px.
- **Line (secondary):** sheet fill with a strong hairline; hover darkens the outline to charcoal.
- **Quiet:** text only in charcoal; hover gets the sheet wash. Used for cancel and inline delete.
- **Danger:** red text with a red hairline at 45% and a red wash on hover. Kept for destructive actions inside edit areas.
- **WhatsApp:** green fill, white glyph, for the wa.me action.
- **Icon:** square at each height.

### Tags
- **Style:** boxed stamps: 1px border in the text's own colour, 2px corners, 11px 700 text, no fill.
- **State:** ok / warn / bad / accent (frozen) / mute (grey text, strong hairline).

### Cards / Containers (the Sheet)
- **Corner Style:** 4px.
- **Background:** sheet white on platinum paper.
- **Shadow Strategy:** none (see The Flat Paper Rule).
- **Border:** 1px hairline; header and footer separated by hairlines; rows divided by soft hairlines.
- **Internal Padding:** 16px inline; rows end in an end-aligned action cluster.

### Inputs / Fields
- **Style:** 44px tall (36px small), sheet white, strong hairline, 3px corners, 15px text, faint placeholder; the label sits above in Label style.
- **Focus:** border turns baby blue with a 3px baby-blue glow at 22%.
- **Select:** custom chevron, mirrored to the left in RTL.

### Navigation
- **Phone:** bottom bar on sheet white at 96% with blur; icon over an 11px 700 label in muted ink; the active item turns ink and gets a 2px baby-blue bar on the top rule.
- **Desktop:** 236px rail with the logo and wordmark above a hairline; 14px items; the active item gets a paper background and a 2px baby-blue bar on its inline-start edge.
- **Filter tabs:** 34px outlined chips in a horizontally scrolling row; the selected one is solid graphite. Segmented controls use the same treatment inside a strong-hairline frame.

### The Tally (signature)
The package is always drawn as boxes, one per session. Played boxes are filled charcoal (amber when renewal is near), the next box is outlined baby blue, and remaining boxes are outlined in strong hairline (red-tinted when expired). Small boxes are 9 by 12px with a 3px gap; large ones are 16 by 22px with a 5px gap. The tally stays LTR in both languages. On load, boxes fill one after another (scaleY from 0.2, 0.42s, 32ms stagger).

### Ledger and Statement (signature)
Uppercase muted keys over Display numerals with a muted "JD" unit and a sub-line, in columns divided by hairlines. On the dashboard the ledger sits inside the charcoal statement panel, headed by the logo mark and a 2px baby-blue top rule, with horizontal bars for received, expected and costs.

### Member Card (signature)
A brushed-metal ID card for each player: metal gradient with a fine vertical grain, logo and wordmark at the top, the uppercase name (19px 800, 0.06em) and the tally at the bottom. A single light sheen passes across it once on load.

### Attendance Tile
A 4px-corner tile at least 84px tall with an 800 name. One tap fills the whole tile with the status colour (white text; dark text on amber), and the mark stamps in like a pen (scale 1.9 and -12deg to rest, 0.38s). Built for use outdoors in daylight.

### Monogram
A 36px square in sheet shade with charcoal 800 initials. This replaces circular avatars.

## Do's and Don'ts

### Do:
- **Do** build every section as a ruled sheet: 1px hairline, 4px corners, header line, rows divided by soft hairlines, each row ending in its action.
- **Do** set every figure in tabular Montserrat with a muted "JD" unit, and use Display size for the numbers that answer the screen's question.
- **Do** draw any session package as a tally of boxes, never as a percentage ring or a progress bar alone.
- **Do** keep baby blue for next, active, focus and link states only.
- **Do** use the RGB-triplet variables with alpha (`rgb(var(--bad) / .45)`) so both themes follow automatically.
- **Do** use logical properties and check every screen in RTL, where tracking and uppercase switch off.
- **Do** honour `prefers-reduced-motion`; the tally fill, stamp and sheen are the only signature motions, all eased with `cubic-bezier(.16,1,.3,1)`.

### Don't:
- **Don't** put shadows on sheets, buttons or tiles; only the statement panel and the member card are lifted.
- **Don't** use gradient KPI tiles or floating soft-shadow cards; ledgers are ruled columns on the sheet.
- **Don't** use emojis anywhere; icons are inline SVG (`_icons.html`).
- **Don't** round corners past 4px on ordinary surfaces, and don't use pill buttons.
- **Don't** add a second accent hue, and don't use the status greens, ambers or reds for decoration.
- **Don't** add a floating chat button; the assistant opens as a drawer from the search icon in the bar.
