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
| Schedule (today) | current/next lesson, e.g. `10:15–11:00 Matematiikka` | `lessons_today`, `lessons_tomorrow`, `lessons` (whole schedule) |
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
actually display that on a dashboard.

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

## Dashboards

Every sensor's full data set is in its **attributes**, readable from any
dashboard card via `state_attr('sensor.xxx', 'attribute_name')`. The plain
**Entities** card only shows the short state text; to render a list, use a
**Markdown** card (Settings → Dashboards → Edit → Add Card → Markdown, or
paste this as YAML in an existing dashboard/view).

Replace `sensor.matti_lukujarjestys` etc. with your actual entity IDs —
check them under **Settings → Devices & Services → Entities**, filtered by
the Wilma device for that student.

### Schedule (today and tomorrow)

```yaml
type: markdown
content: |
  **Today**
  {% set lessons = state_attr('sensor.matti_lukujarjestys', 'lessons_today') or [] %}
  {% if lessons %}
  {% for lesson in lessons %}
  - **{{ lesson.start }}–{{ lesson.end }}** {{ lesson.subject }}{% if lesson.teacher %} ({{ lesson.teacher }}){% endif %}
  {% endfor %}
  {% else %}
  No lessons today.
  {% endif %}

  **Tomorrow**
  {% set lessons_tmrw = state_attr('sensor.matti_lukujarjestys', 'lessons_tomorrow') or [] %}
  {% if lessons_tmrw %}
  {% for lesson in lessons_tmrw %}
  - **{{ lesson.start }}–{{ lesson.end }}** {{ lesson.subject }}{% if lesson.teacher %} ({{ lesson.teacher }}){% endif %}
  {% endfor %}
  {% else %}
  No lessons tomorrow.
  {% endif %}
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

### One dashboard view per student

The cards above are per-sensor. To get a full one-page overview per student,
put several Markdown cards (or the equivalent using the **auto-entities**
HACS card, if installed, keyed on the device) into one dashboard **view**,
one view per child — that mirrors how the sensors are already grouped (one
HA device per student).

## Installing the package

You received this as `wilma-ha.zip`. Unzip it — you get a folder containing
`custom_components/wilma/`. That `custom_components/wilma` folder needs to
end up inside your Home Assistant **config** directory, at
`/config/custom_components/wilma`. Three ways to get it there, pick whichever
you already have access to:

### Option A — File Editor app (works over the internet, no LAN needed)

1. In the HA web UI (e.g. `https://smarthome.arvekari.fi`), go to
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

### After any of the above

1. **Settings → System → Restart** Home Assistant (a full restart, not just
   a reload — new custom integrations need it).
2. **Settings → Devices & Services → Add Integration**, search for
   **Wilma**, and follow the setup wizard (Wilma address, username,
   password, optional MFA, then pick which student(s) to track).
3. Repeat step 2 for each additional Wilma account/school.

### Optional: install via HACS instead (adds update notifications)

HACS itself can't install a bare zip — it needs a Git repository. If you
want update tracking through HACS:

1. Push the contents of this folder to your own GitHub repo (public or
   private — HACS supports both, private needs a token).
2. In HA: **HACS → the "⋮" menu → Custom repositories** → add your repo URL,
   category **Integration**.
3. Find "Wilma" in HACS → **Download**.
4. Restart HA, then add the integration as in step 2/3 above.

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
