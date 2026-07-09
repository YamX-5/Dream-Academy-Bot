# DA — Dream Academy Manager

Basketball academy management app — Mafraq, Jordan. A temporary tool until the real mobile app is ready.

## Two ways to run it

| Mode | How | When to use |
|---|---|---|
| **Online (recommended)** | Deploy once to PythonAnywhere — see [DEPLOY.md](DEPLOY.md) | Permanent URL, works from any phone, laptop can stay off |
| **Local** | Double-click `start.bat` on the laptop | Fallback / testing; laptop must stay on and online |

## Local mode

`start.bat` starts the server and a Cloudflare tunnel that prints a public link
(`https://xxxx.trycloudflare.com`) reachable from any network. Open
`http://127.0.0.1:8000/qr` on the laptop to get the QR for coaches.
The tunnel link changes on every restart — send coaches the new one each time.
On the laptop itself, `http://127.0.0.1:8000` logs you in as admin with no PIN.

## Language

The UI is English by default. The AR / EN button in the top bar switches the whole
app between English (LTR) and Jordanian Arabic (RTL); the choice is remembered per
device. WhatsApp messages to parents and the session summary always stay in Arabic.

## PINs

| Role | Default PIN | Access |
|---|---|---|
| Coach | `1234` | Attendance screen only |
| Admin | `0000` | Everything |

Change both in Settings before first real use — the PIN is the only protection on
any link that is reachable from the internet.

## Subscription rules

- 20 JD = 12 sessions, valid 35 days.
- Present = one session deducted. Absent/excused = no deduction (a settings flag can enable deduction on absence).
- A player without a subscription can still be marked present — they appear in the red "Unpaid" list on the dashboard.
- Freezing pauses the clock: on unfreeze, the expiry date extends by the frozen duration.

## Backups

- Automatic daily + on every start, into `backups/` (last 30 kept).
- Full Excel auto-export weekly into `exports/`, plus an "Export all" button on the dashboard.

## First-time player import

From the Players page: download the players template, fill it in Excel, and upload it.
