---
version: 1
slug: "templates-base-html"
primary_target: "templates/base.html"
related_targets: ["templates/dashboard.html","templates/attendance.html","templates/finance.html","templates/player_card.html"]
---

# Surface brief: Dream Academy console (all admin + coach screens)

Scope: every screen of the Flask app (dashboard, attendance, players, player card, finance, settings, groups, insights, login, receipt). Mode: Operate. Owner on phone and laptop equally; coaches on phones outdoors.

Job: see money and players at a glance, act on the next renewal/debt/cost, take attendance in one tap per player.

## Direction contract

THESIS: The academy's books kept like an official basketball scoresheet printed on platinum stock: ruled hairline grids, boxed tallies, big tabular numerals. Refuses the category default of floating soft-shadow cards, gradient KPI tiles and a chat-bubble FAB.

OWN-WORLD: Graphite ink (#14161B) on cool platinum paper (#F3F4F6) in light; deep graphite (#0F1115) with platinum ink in dark. One accent only, the logo's baby blue (#6EA3EE), used for state and the active row, never as decoration. Charcoal #4A4B50 from the logo's A for secondary ink. Hairline 1px rules carry all structure; radius 2-4px. Montserrat (the logo's face) for numerals and headings, tabular; IBM Plex Sans Arabic is banned by reflex list, so Arabic uses Tajawal; Latin body Montserrat 500. Labels are small caps tracked. The 12-session package is always drawn as 12 boxes (filled = played, outlined = left), the scoresheet's running tally. Player page carries a brushed-metal member card.

STORY: Owner opens the app and reads, top to bottom like a scoresheet header: cash in the box, owed to you, this month landing; then ranked rows: renewals by days left, debts by amount, today's bookings. Every row ends in its action.

FIRST VIEWPORT: Phone: logo mark + month at top rule; a two-column ledger header (Cash in box | Owed to you) at 34px tabular numerals; a single line "Month lands at X JD" with received/expected/costs; then the Renewals tally table. Desktop: left rail nav with logo, same ledger header across three columns, renewals and owed side by side.

FORM: Platinum scoresheet, own grounded candidate 3 of 7 (FIBA official scoresheet), fused with the pinned Amex-premium feel; seed key 9d349f47. Raises: hairline-grid discipline (design annual plate section), bar length = duration (labanotation), rows ranked live by time (split-flap board).

SIGNATURE: the 12-box tally fills box by box when a page loads (staggered 30ms), and attendance taps stamp the player's row like a scorer's pen (scale-in check, row ink change).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
