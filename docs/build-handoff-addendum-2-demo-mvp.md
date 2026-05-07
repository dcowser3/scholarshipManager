# Build Handoff - Addendum 2 (Demo MVP)

## What this is

This supersedes addendum 1 for the demo build. Addendum 1 described a production-grade implementation. This document describes a proof-of-concept the stakeholder will use to demo capabilities to school staff.

Read addendum 1 for the concepts such as email intake, budgets, and collisions. This document tells you what to actually build for the demo. When in doubt, follow this. Addendum 1's restrictions are aspirational for production, not requirements for the demo.

The demo flow:

1. Stakeholder sets up a Gmail account such as `toledo-aid-demo@gmail.com`.
2. Someone at the school emails it with a plain-English change request.
3. System parses with an LLM, then emails back a confirmation with a numeric breakdown.
4. Recipient replies `yes` or `no` from any device, including mobile.
5. System generates the documents, Adjustment of Aid `.xlsx` and Tender PDF, and emails them to the stakeholder's own email address as attachments.
6. Stakeholder shows that email thread to school staff as proof the workflow works.

That's it. No production hardening, no FERPA review, no admin queues, no escalation paths, and no web app for confirmation.

## What to build for Phase 4 (demo version)

### 4a. Inbox polling

- Connect to the Gmail account via IMAP with an app password. Stakeholder will provide credentials via env vars.
- Poll every 60 seconds for new messages in `INBOX`.
- Mark processed messages as read so they are not reprocessed.
- Store a row in `email_intake` for every received message.

Why IMAP instead of the Gmail API? IMAP works in roughly 20 lines of Python with `imaplib`. Gmail API needs OAuth setup. For a demo, IMAP wins.

### 4b. Sender check (lightweight)

- Read allowed senders from config value `email.allowed_senders` as a comma-separated list, for example `"coach1@school.edu, demo@stakeholder.com"`.
- If the sender is not in the list, log it and ignore it. No bounce and no notification.

That is the entire sender-authorization story for the demo. The whitelist table from addendum 1 is not needed.

### 4c. Parsing

- Use Claude via the Anthropic API.
- Temperature `0`.
- Single call per email.
- Pass the email body with HTML stripped and quoted reply text stripped, plus the current roster for the sport associated with the sender, including athlete names and Rocket numbers.
- Use a second config value for sport mapping: `email.sender_sports` as JSON, for example `{"coach1@school.edu": "Football"}`.
- Prompt the model to output structured JSON with the fields described in addendum 1 section `6.2`.

If the model returns ambiguous or low-confidence results, just include the issues in the confirmation email so the recipient sees them. There is no multi-round clarification flow in the demo.

### 4d. Confirmation flow (reply-based)

After parsing, send a confirmation email to the original sender with:

- A plain-text summary of what was understood
- A numeric table of every change: athlete name, field, term, before, after, delta
- A budget impact line such as `After change: 87% of budget`
- A clear instruction: `Reply YES to confirm, or NO to cancel. To change anything, send a new email.`

The system polls the inbox using the same IMAP loop as section 4a. When a reply arrives:

1. Match the reply to a pending request via the `In-Reply-To` header and look up `email_intake.message_id`.
2. Strip quoted content from the reply body, including lines starting with `>` or everything after `On <date>, <person> wrote:`. Most mobile email clients quote the full original message, and we only care about what the user typed.
3. Normalize the remaining text by lowercasing and trimming whitespace, then check:
   - Confirmations: `yes`, `y`, `confirm`, `confirmed`, `approve`, `approved`, `ok`, `okay`, `go`
   - Rejections: `no`, `n`, `cancel`, `stop`, `reject`, `decline`
   - Anything else: respond asking the recipient to reply `YES` or `NO`, or send a new email if they want to change something
4. On confirmation, write `submissions` and `adjustments` rows, trigger document generation, and email the docs.
5. On rejection, mark the intake row as `CANCELLED` and send a brief acknowledgment.

Match security for the demo is:

- Reply must come from the original sender address
- Reply must have an `In-Reply-To` header matching the confirmation email's `Message-ID`
- Request must not already be confirmed

That is enough for a demo.

No web confirmation page, no token, and no link. The reply lives entirely in the email client, so it is mobile-friendly by default.

### 4e. Document delivery

After confirmation:

1. Generate the Adjustment of Aid `.xlsx` and Tender PDF using the Phase 3 pipeline.
2. Email them as attachments to the demo recipient address from `email.demo_recipient`, which is the stakeholder's own email.
3. Use subject line `[DEMO] Generated documents for <athlete name>`.
4. Mark the `email_intake` row as `COMPLETED`.

For the demo, this is the entire send story. No staging, no queues, no DocuSign, and no Financial Aid routing. Just an email with attachments to the stakeholder's inbox.

### 4f. UI integration (minimal)

- Email-derived submissions write to the same `submissions` and `adjustments` tables as UI submissions, so the existing sport pages already show them with pending indicators.
- Add a `source` column to `submissions` with values `'UI'` or `'EMAIL'`. Display it as a small badge on the row.
- Collision detection should stay simple. When a new submission targets a field that already has a `SUBMITTED` adjustment, mention it in the confirmation email's numeric table, for example with a note like `already pending`. The UI can show the same indicator. No special UI panel is needed for the demo.

## What about Phase 3.5 (budgets)?

Same as addendum 1, but simpler:

- Add a `sport_budgets` table, mock-seeded at `1.25x` current allocation.
- Show it on sport pages as a banner such as `Budget $X / Allocated $Y (Z%)`.
- Show it in the confirmation email and confirmation page as `After change: ZZ% of budget`.
- Warn only. No blocking and no override flow.

Skip the admin UI for editing budgets in the demo. Seed via script.

## Schema (minimal additions for demo)

```sql
sport_budgets (
  id              serial PRIMARY KEY,
  sport_id        int references sports(id),
  academic_year   text not null,
  budget_amount   numeric(12,2) not null,
  notes           text,
  unique(sport_id, academic_year)
)

email_intake (
  id                       uuid PRIMARY KEY,
  received_at              timestamptz,
  sender_email             text,
  inbound_message_id       text,
  raw_body                 text,
  parsed_payload           jsonb,
  confirmation_message_id  text,
  state                    text,
  submission_id            uuid references submissions(id) null,
  created_at               timestamptz,
  updated_at               timestamptz
)

ALTER TABLE submissions ADD COLUMN source text default 'UI';
ALTER TABLE submissions ADD COLUMN intake_id uuid references email_intake(id) null;
```

Field notes:

- `inbound_message_id` is the `Message-ID` of the inbound email.
- `raw_body` can store plain text only for the demo.
- `confirmation_message_id` is the `Message-ID` of the system-generated confirmation email, and replies match against this.
- `state` is one of `RECEIVED`, `PARSED`, `AWAITING_CONFIRMATION`, `CONFIRMED`, `CANCELLED`, `COMPLETED`, or `PARSE_FAILED`.

Skip these from addendum 1 for the demo:

- `email_authorized_senders` table, because config string is enough
- `pending_email_requests`, because that state can collapse into `email_intake`
- Full raw-MIME blob storage, because plain-text body is fine
- Versioned parser tracking, clarification round counters, and similar production bookkeeping

## Config values needed

Stakeholder provides these through env vars or a config table:

```ini
email.imap_host           = imap.gmail.com
email.imap_user           = <gmail address>
email.imap_password       = <gmail app password>
email.allowed_senders     = "coach1@school.edu, ..."
email.sender_sports       = {"coach1@school.edu": "Football", ...}
email.demo_recipient      = <stakeholder email>
email.from_address        = <gmail address, same as imap_user>
anthropic.api_key         = <key>
```

## What is intentionally not in the demo

Do not build these. They belong to addendum 1 and the production path, not the demo.

- SPF, DKIM, or DMARC validation
- The `email_authorized_senders` whitelist table
- Multi-round clarification flow
- A web confirmation page or confirmation link
- Authenticated confirmation page
- Admin email-intake dashboard
- Staged-send queues for outbound documents
- DocuSign integration
- Sending documents to Financial Aid
- Encrypted-at-rest raw MIME storage
- An anti-pattern lecture in the codebase

If the demo goes well and a production build is greenlit, addendum 1 becomes the upgrade path. None of the demo work is wasted. It just needs hardening at the edges.

## What must still be true in the demo

A few things from addendum 1 still matter even for a five-minute demo:

1. The confirmation email shows the actual numbers: athlete, field, term, before, after, delta. A one-line summary alone is not enough. If the LLM misreads `by $500` as `to $500` and the audience catches it after confirmation, the demo is dead. The numeric table is what makes the LLM piece defensible.
2. The AI does not guess on ambiguity. If two players have the same last name and the email says `Smith`, the parser flags it. The confirmation email shows the flag. The recipient can decide what to do, but the system does not silently pick one.
3. `submissions.source = 'EMAIL'` is set so the UI shows email-derived submissions distinctly. This is part of the demo story: both channels stay in sync.
4. The pending state still works. The demo flow writes the same `submission` and `adjustment` records as the UI flow, so pending indicators show up correctly on the sport page.

## Suggested demo script

For the actual demo to school staff:

1. Open the sport page for one team and show the current roster, the budget banner, and an existing record.
2. Switch to the inbox on a phone to make the mobile-friendliness obvious. Send an email to the demo Gmail account: `Please change John Smith's tuition aid for spring to $5,200 and his room to $2,800.`
3. Wait about 30 seconds and show the confirmation email with the numeric table.
4. Tap reply, type `yes`, and send.
5. Wait about 30 seconds and show the email with the generated Adjustment of Aid `.xlsx` and Tender PDF as attachments.
6. Switch back to the sport page and show the new pending indicator on John Smith's row.

Three taps on a phone, end to end, in about five minutes.
