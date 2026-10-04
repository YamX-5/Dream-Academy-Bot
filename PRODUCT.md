# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Owner (Yaman, admin):** runs Dream Academy, a basketball academy in Mafraq, Jordan. Manages players, groups, subscriptions, payments, coach salaries and costs. Uses the app on phone and laptop about equally.
- **Coaches:** open the app on their phones at the gym to take attendance (shared coach PIN, attendance-only access). They can quick-add a new player, which waits for owner approval.

## Product Purpose

One place to run the academy without losing money or track: who is training, who has paid, who owes, what the academy spent, and what is left. Success = no missed renewals, no unpaid sessions slipping through, and an honest cash picture even when payments arrive unevenly week to week.

## Positioning

Built around how this academy actually bills: a package is 12 sessions for 20 JD that run on the calendar (training days), attended or not. Attendance is recorded for the record, not for billing. Freezing a player pauses their calendar.

## Operating Context

- Training days are currently Sunday, Tuesday, Thursday and change over time; a change applies from a chosen date and never rewrites past sessions. Days off (Eid, court closed) extend everyone's package.
- Payments are cash or CliQ, each player may pay a different amount; partial payments leave a balance owed.
- Renewals are sometimes recorded late, so start date and payment date are chosen before saving.
- Session costs are per booking: court 5 JD without lights, 10 JD with lights; water about 1.5 JD (1 JD when it is cold). Several groups in one day = several bookings. Quantities are logged per session.
- Coaches are paid monthly or per session; a per-session coach who does not work is not paid. Each coach's salary is tracked as Due or Paid per month.
- Parent communication happens on WhatsApp (wa.me links, Arabic templates).
- Hosted on PythonAnywhere (Flask + SQLite); also runs locally on a laptop with a Cloudflare tunnel.

## Capabilities and Constraints

- Flask + Jinja templates + Tailwind via CDN, SQLite, no build step. Schema changes must migrate live data in place (`database._migrate`).
- Bilingual UI: English default, Arabic with Jordanian dialect, full RTL.
- Roles: admin (full), coach (attendance only).
- Currency is JD (Jordanian dinar).

## Brand Commitments

- Name: Dream Academy. Logo: "DA" monogram (baby-blue D, charcoal A with a swoosh) above the wordmark DREAM ACADEMY in a bold geometric sans. Source image supplied by the owner (screenshot, no vector file).
- No emojis anywhere; the owner finds them childish. Icons are inline SVG.
- The owner wants a premium, restrained feel (reference: the American Express app) that does not look AI-generated.

## Evidence on Hand

- Real academy data lives in the live database; no testimonials, customers or marketing claims exist and none may be invented.

## Product Principles

1. Never lose money quietly: every unpaid session, balance and unpaid salary is visible somewhere the owner looks daily.
2. Dates are always editable before saving; the real world gets recorded late.
3. Fast at the gym: attendance is one tap per player, readable outdoors.
4. Past numbers do not move when settings change.
