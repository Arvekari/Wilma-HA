# Wilma for Home Assistant

<a href="https://www.buymeacoffee.com/arvekari"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="150"></a>

Custom Home Assistant integration for Finland's Wilma school system —
schedules, homework, exams, grades, attendance notes (merkinnät), messages,
and news, as entities under **Settings → Devices & Services**. Login and
settings are managed entirely from the HA UI (Config Flow) — no YAML.

Python port of the authentication/parsing logic from the open-source
[`aikarjal/wilmai`](https://github.com/aikarjal/wilmai) project (MIT
licensed). See [`LICENSE`](LICENSE).

## What you get

Per selected student, one HA **device** with these sensors:

| Entity | State (short text) | Key attributes (full content) |
|---|---|---|
| Schedule (today) | current/next lesson, e.g. `Maanantai 10:15–11:00 Matematiikka` | `weekday_today`, `lessons_today`, `next_school_day`, `weekday_next_school_day`, `lessons_next_school_day`, `next_school_day_skips_a_weekday`, `lessons` (whole schedule) |
| Homework | most recent item, e.g. `Matematiikka: s.42 teht. 1-5` | `count`, `items` |
| Upcoming exams | next exam, e.g. `2026-02-20 Matematiikka: Koe2` | `count`, `upcoming_exams` |
| Grades | latest grade | `recent_grades` |
| Attendance notes | most recent note, e.g. `MA: Selvittämätön poissaolo` | `count`, `lesson_notes` — merkinnät |
| Messages | most recent subject | `count`, `recent_messages` |
| News | most recent title | `count`, `recent_news` |
| Actionable summary | actionable item count | `items`, `counts` — rule-based triage (see caveat below) |

**Why the state is a short summary, not the whole list:** a Home Assistant
sensor's `state` is capped at 255 characters and is meant to be one glance-able
value (that's also what shows on a dashboard tile by default). The full data
— every lesson, every homework item, every message — always lives in the
entity's **attributes**, never truncated. See **Dashboards** below for how to
actually display that.

**School-week awareness:** the schedule sensor understands Mon–Fri school
weeks, not just "today +1 day". `next_school_day` is the next date that
*actually has lessons* in Wilma's own data — on a Friday it correctly points
at the following Monday. If a public holiday closes school mid-week (e.g.
Wednesday), it correctly jumps Tuesday straight to Thursday instead of
Wednesday, and `next_school_day_skips_a_weekday` flags that a weekday got
skipped so you can call it out on a dashboard or in an automation. This
depends on how far into the future Wilma's `/overview` response reaches —
long breaks (e.g. a week-long winter holiday) may not show up until the data
window reaches them.

**Triage caveat:** the "Actionable summary" sensor ports the *deterministic*
part of the original wilma-triage skill (lesson-note type keywords, sender/
subject keyword matching, date-proximity for exams/homework). The original
skill also had an LLM read full message/bulletin text to catch buried
logistics ("school starts at 9:30 tomorrow, bring skis") — that's language
understanding, not a fixed rule, so it isn't replicated in Python. Pair this
sensor with an automation that hands `content`/`recent_messages` to a
conversation agent if you want that behaviour back.

**Multiple accounts:** the integration has no single-instance limit. Add it
again from **Settings → Devices & Services → Add Integration → Wilma** for
each separate Wilma login/school (e.g. one child in Vantaa's Wilma, another
in Mercuria's) — each becomes its own independent config entry with its own
login session and its own device(s).

## Installing the package

You received this as `wilma-ha.zip`. Unzip it — you get a folder containing
`custom_components/wilma/`. That `custom_components/wilma` folder needs to
end up inside your Home Assistant **config** directory, at
`/config/custom_components/wilma`. Three ways to get it there, pick whichever
you already have access to:

### Option A — File Editor app (works over the internet, no LAN needed)

1. In the HA web UI (e.g. `https://haosinstallation.url`), go to
   **Settings → Add-ons → File editor** (install it from the Add-on Store
   first if it's not there) and open its **Web UI**.
2. If there's no `custom_components` folder at the root, create it.
3. Use the editor's upload/new-file tools to recreate the `wilma` folder
   under `custom_components/` with the same files from the zip. (The File
   Editor add-on's UI uploads one file at a time — for a whole folder tree
   the SSH option below or the Samba option is faster.)

### Option B — SSH & Web Terminal app (fastest, works over the internet)

1. **Settings → Add-ons → Advanced SSH & Web Terminal → Open Web UI**
   (or SSH in from a terminal if you've set up a key).
2. Get the zip onto the HA host — e.g. `scp wilma-ha.zip root@<host>:/tmp/`,
   or `wget`/`curl` it from wherever you're hosting the file, or paste it in
   via the terminal's own file transfer if it has one.
3. Then:
   ```bash
   cd /config
   mkdir -p custom_components
   unzip -o /tmp/wilma-ha.zip -d /tmp/wilma-ha-extracted
   cp -r /tmp/wilma-ha-extracted/custom_components/wilma custom_components/
   ```

### Option C — Samba share mount (from your own Mac/PC)

1. **Settings → Add-ons → Samba share → Start** (install it first if needed).
2. On your Mac: Finder → **Go → Connect to Server** →
   `smb://<your-ha-host>` → mount the `config` share.
3. Assuming it's mounted and you're `cd`'d into it (adjust the path to
   wherever you unzipped the package, e.g. `~/Desktop/zip_purku/wilma`):
   ```bash
   # Go to HA's config folder (the mounted Samba share)
   cd /Volumes/config

   # Make sure custom_components exists
   mkdir -p custom_components

   # Copy the integration folder in
   cp -r ~/Desktop/zip_purku/wilma custom_components/
   ```

### Optional: install via HACS instead (adds update notifications)

HACS itself can't install a bare zip — it needs a Git repository. If you
want update tracking through HACS:

1. Push the contents of this folder to your own GitHub repo (public or
   private — HACS supports both, private needs a token).
2. In HA: **HACS → the "⋮" menu → Custom repositories** → add your repo URL,
   category **Integration**.
3. Find "Wilma" in HACS → **Download**.
4. Restart HA (see next section), then configure it as below.

## Configuring the integration

### First-time setup (Config Flow)

1. After installing the files (any option above), do a full
   **Settings → System → Restart** of Home Assistant — a new custom
   integration's code isn't picked up by a reload, it needs a restart.
2. **Settings → Devices & Services → Add Integration**, search for **Wilma**.
3. **Step 1 — Connect to Wilma:** enter your school's Wilma address (e.g.
   `https://ville.inschool.fi`) and your own Wilma username/password. Each
   person sets this up with their **own** login — nothing is shared.
4. **Step 2 — MFA (only if your account has it enabled):** enter a one-time
   code from your authenticator app, or paste your TOTP secret /
   `otpauth://` URI once so future refreshes authenticate automatically
   without asking again.
5. **Step 3 — Choose students:** every child found on that Wilma login is
   listed; pick which ones should get sensors. (If a Wilma account has
   several children under the same login — e.g. two kids on the same
   school's Wilma — they're now correctly separated into independent
   entities/devices; see the multi-student fix in the changelog below.)
6. Done — a device appears per selected student, each with the sensors from
   the table above. Repeat step 2 onward for another school/account (see
   **Multiple accounts** above).

### Changing settings later (Options Flow)

Go to **Settings → Devices & Services → Wilma → [the account you want to
change] → Configure** (the gear icon). From there you can:

- Change which students are active (add/remove without deleting the whole
  integration entry).
- Change the refresh interval (default 30 minutes; 5–240 minutes allowed).

Changing options triggers an automatic reload of that entry — no restart
needed. Login credentials themselves aren't editable from Options; to change
those, remove the integration entry and add it again.

## Dashboards

Every sensor's full data set is in its **attributes**, readable from any
dashboard card via `state_attr('sensor.xxx', 'attribute_name')`. The plain
**Entities**/tile cards only show the short state text; to render a full
list, use a **Markdown** card.

### Finding your entity IDs

**Settings → Devices & Services → Wilma → [account] →** click the student's
device to see all its entities, or **Settings → Devices & Services →
Entities** and filter/search by student name. Entity IDs look like
`sensor.matti_lukujarjestys` — swap every example below for your real ones.

### Adding a Markdown card through the UI

1. Open the dashboard you want, click **Edit Dashboard** (pencil, top right).
2. **Add Card → Markdown** (search "Markdown" if it's not visible).
3. Paste the `content:` text from one of the examples below into the card's
   content box (skip the surrounding `type: markdown` / `content: |` lines —
   the UI card editor's text box *is* the content).
4. Save. For the exact YAML shown below (including `type:`), instead open
   the card editor and switch to **Edit in YAML** (three-dot menu → Edit in
   YAML) and paste the whole block.

### Schedule (today and next school day)

```yaml
type: markdown
content: |
  **{{ state_attr('sensor.matti_lukujarjestys', 'weekday_today') }} (tänään)**
  {% set lessons = state_attr('sensor.matti_lukujarjestys', 'lessons_today') or [] %}
  {% if lessons %}
  {% for lesson in lessons %}
  - **{{ lesson.start }}–{{ lesson.end }}** {{ lesson.subject }}{% if lesson.teacher %} ({{ lesson.teacher }}){% endif %}
  {% endfor %}
  {% else %}
  Ei tunteja tänään.
  {% endif %}

  **{{ state_attr('sensor.matti_lukujarjestys', 'weekday_next_school_day') }} (seuraava koulupäivä, {{ state_attr('sensor.matti_lukujarjestys', 'next_school_day') }})**
  {% if state_attr('sensor.matti_lukujarjestys', 'next_school_day_skips_a_weekday') %}
  ⚠️ Vapaapäivä väliin jää — tarkista syy Wilman tiedotteista.
  {% endif %}
  {% set next_lessons = state_attr('sensor.matti_lukujarjestys', 'lessons_next_school_day') or [] %}
  {% for lesson in next_lessons %}
  - **{{ lesson.start }}–{{ lesson.end }}** {{ lesson.subject }}{% if lesson.teacher %} ({{ lesson.teacher }}){% endif %}
  {% endfor %}
```

### Homework

```yaml
type: markdown
content: |
  {% for hw in state_attr('sensor.matti_laksyt', 'items') %}
  - **{{ hw.date }}** {{ hw.subject }}: {{ hw.homework }}
  {% endfor %}
```

### Upcoming exams

```yaml
type: markdown
content: |
  {% for exam in state_attr('sensor.matti_tulevat_kokeet', 'upcoming_exams') %}
  - **{{ exam.date }}** {{ exam.subject }}: {{ exam.name }}{% if exam.topic %} — {{ exam.topic }}{% endif %}
  {% endfor %}
```

### Grades

```yaml
type: markdown
content: |
  {% for g in state_attr('sensor.matti_arvosanat', 'recent_grades') %}
  - **{{ g.date }}** {{ g.subject }}: {{ g.name }} — {{ g.grade }}
  {% endfor %}
```

### Attendance notes (merkinnät)

```yaml
type: markdown
content: |
  {% for note in state_attr('sensor.matti_merkinnat', 'lesson_notes') %}
  - {% if note.start %}**{{ note.start }}–{{ note.end }}** {% endif %}{{ note.subject }}: {{ note.type_label }}{% if note.teacher %} ({{ note.teacher }}){% endif %}
  {% endfor %}
```

### Messages

```yaml
type: markdown
content: |
  {% for m in state_attr('sensor.matti_viestit', 'recent_messages') %}
  - **{{ m.subject }}**{% if m.sender_name %} — {{ m.sender_name }}{% endif %}
  {% endfor %}
```

### News

```yaml
type: markdown
content: |
  {% for n in state_attr('sensor.matti_tiedotteet', 'recent_news') %}
  - **{{ n.title }}**{% if n.author %} — {{ n.author }}{% endif %}
  {% endfor %}
```

### Actionable summary (triage)

```yaml
type: markdown
content: |
  {% for item in state_attr('sensor.matti_toimenpiteet', 'items') %}
  - [{{ item.bucket }}] {{ item.text }}
  {% endfor %}
```

### Full example: one dashboard view per student

To build a complete one-page overview for one child, create a new
**Dashboard view** (Edit Dashboard → the `+` next to the view tabs at the
top) named after the student, then switch that view to **Edit in YAML**
(three-dot menu on the view) and paste all the cards together, e.g.:

```yaml
title: Matti
cards:
  - type: markdown
    title: Lukujärjestys
    content: |
      **{{ state_attr('sensor.matti_lukujarjestys', 'weekday_today') }} (tänään)**
      {% for lesson in state_attr('sensor.matti_lukujarjestys', 'lessons_today') or [] %}
      - **{{ lesson.start }}–{{ lesson.end }}** {{ lesson.subject }}
      {% endfor %}
  - type: markdown
    title: Läksyt
    content: |
      {% for hw in state_attr('sensor.matti_laksyt', 'items') %}
      - **{{ hw.date }}** {{ hw.subject }}: {{ hw.homework }}
      {% endfor %}
  - type: markdown
    title: Tulevat kokeet
    content: |
      {% for exam in state_attr('sensor.matti_tulevat_kokeet', 'upcoming_exams') %}
      - **{{ exam.date }}** {{ exam.subject }}: {{ exam.name }}
      {% endfor %}
  - type: markdown
    title: Toimenpiteet
    content: |
      {% for item in state_attr('sensor.matti_toimenpiteet', 'items') %}
      - [{{ item.bucket }}] {{ item.text }}
      {% endfor %}
```

Repeat as a separate view per child — this mirrors how the sensors are
already grouped (one HA device per student). If you have the
**auto-entities** HACS card installed, you can use it instead to
automatically pull in every entity belonging to a device, so new sensors
show up without editing the dashboard again.

## Security notes

- Your Wilma username/password are stored the same way every other HA
  integration stores credentials: inside HA's own config-entry storage
  (`.storage/core.config_entries`) on your HA host. This is standard HA
  practice, not something specific to this integration — treat your HA
  backups accordingly.
- Every person/child-account combination who wants sensors sets it up with
  their **own** Wilma login via the Add Integration wizard. Nothing is
  shared between config entries.
- `iot_class: cloud_polling` — this integration only ever talks to your
  school's Wilma server and (for external bulletin attachments) whatever
  external URL the bulletin links to, using an isolated, unauthenticated
  request that never carries Wilma credentials.

## Credits

Wilma authentication/parsing logic originally by
[aikarjal/wilmai](https://github.com/aikarjal/wilmai) (MIT license). This
repository is an independent Python port for Home Assistant, unaffiliated
with Visma/Wilma.

<a href="https://www.buymeacoffee.com/arvekari"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="150"></a>
