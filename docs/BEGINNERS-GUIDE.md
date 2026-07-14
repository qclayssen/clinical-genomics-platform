# Beginner's Guide — what this project actually does

No background assumed. If a word looks like jargon, it's defined in
[GLOSSARY.md](GLOSSARY.md). Read this first, keep the glossary open in another tab.

---

## The one-sentence version

**We take raw DNA sequencing data, find the genetic differences in it, check our answers
against a known-correct answer key, save the results in a database, show them on a
dashboard, and have an AI write a plain-language summary — all automatically and in a way
you could audit later.**

That's it. Everything below is just the detail of *how*.

---

## Why would anyone build this?

Hospitals and labs increasingly read a patient's DNA to help diagnose disease. Reading DNA
produces an enormous pile of raw data that is useless until software turns it into a short,
trustworthy list of "here are the meaningful differences in this person's genome."

That software has to be:
- **Correct** — a wrong answer can mean a wrong diagnosis.
- **Reproducible** — run it twice, get the same answer.
- **Traceable** — months later you must be able to prove exactly how a result was produced.

This project is a *portfolio demonstration* of building that kind of software. It uses
**public practice data**, not real patients, and is **not a certified medical device**. It
exists to show an employer "I can build this responsibly."

---

## The journey of one DNA sample, step by step

Think of it like a factory assembly line. Raw material goes in one end; a finished,
inspected product comes out the other.

### Step 1 — Raw material arrives: FASTQ files
A **sequencing machine** reads a DNA sample and spits out millions of short text fragments
called **reads** — each is a few hundred letters of `A`, `C`, `G`, `T` (the DNA alphabet).
These are stored in **FASTQ** files. On their own they're meaningless, like dumping a
shredded book on a table.

### Step 2 — Quality check: "is this data any good?"
Before doing anything clever, we check the raw reads for problems (junk sequences, low
quality). Tools: **FastQC** and **fastp**. This is the incoming-goods inspection.

### Step 3 — Putting the puzzle together: alignment
We take each short fragment and figure out *where it belongs* on the known human
**reference genome** (a standard "template" human DNA sequence). This is called
**alignment**, and the tool is **BWA-MEM2**. Result: a **BAM** file — the shredded book,
now with every scrap taped back into roughly its right page.

### Step 4 — Removing accidental copies: mark duplicates
The lab process sometimes photocopies the same fragment many times by accident. We flag
those duplicates so they don't fool us into thinking a difference is more common than it
is. Tool: **MarkDuplicates**.

### Step 5 — Finding the differences: variant calling
Now the actual science. We compare the sample against the reference genome and record every
spot where this person differs — a **variant**. The output is a **VCF** file, essentially
the list "at position X, this person has a G where the reference has an A." Tools:
**GATK HaplotypeCaller** or **DeepVariant**.

### Step 6 — Grading our own homework: validation
How do we know our variant list is right? We use a **truth set** — a sample
(**GIAB HG002**) whose *correct* answer is already known and published. We compare our
answer to the answer key and compute a score:
- **Precision** — of the variants we reported, how many were real? (few false alarms)
- **Recall** — of the real variants, how many did we catch? (few misses)
- **F1** — a single number combining both.

Tool: **hap.py**. This step is what turns a school project into something a lab would take
seriously — we don't just produce an answer, we *prove how good the answer is*.

### Step 7 — Packaging the result: structured output + provenance
We bundle the key numbers into a tidy **JSON** file, and — crucially — stamp it with
**provenance**: which exact version of the software ran, which reference was used, and a
**checksum** (digital fingerprint) of every input file. This is the "manufacturing record"
that lets someone reconstruct exactly what happened.

### Step 8 — Filing it away: the database
The results and their provenance go into a **PostgreSQL** database. Ours is deliberately
**insert-only**: you can add records but never secretly edit or delete them. Corrections are
new entries. This mirrors how medical records work — you never erase, you amend.

### Step 9 — The morning dashboard: Metabase
A lab manager doesn't read database tables. **Metabase** turns the data into charts: how
many samples passed, how long each took, quality trends over time. This is the screen a lab
director would glance at with their coffee.

### Step 10 — The AI writes the summary
Finally, an **AI language model** reads the structured result and drafts a
**plain-language paragraph** ("Sample HG002 passed validation; precision was 99.8%..."). It
**always** stamps the draft "REQUIRES CLINICIAN REVIEW" and cites which number came from
where. The AI drafts; a human signs. It never makes a medical decision.

---

## Where does each buzzword from the résumé live?

The project brief asked for six named technologies. Here's each one in one line, and where
to look:

| Buzzword | Plain meaning | Where in the repo |
|---|---|---|
| **Nextflow** | The tool that runs steps 2–7 in order, automatically | `pipeline/` |
| **AWS CDK** | Code that sets up rented cloud computers to run it at scale | `infra/` |
| **PostgreSQL** | The filing cabinet (database) for results | `db/` |
| **Metabase** | The charts/dashboard | `dashboards/` |
| **Fine-tuning / LLM** | Teaching an AI to write the summaries | `ai-report/` |
| **Docker** | Sealed boxes so the software runs identically everywhere | `docker/`, referenced in every pipeline module |

---

## The two big ideas that make this "clinical-grade" not "toy"

If you remember nothing else, remember these two:

1. **We grade ourselves against a known answer key** (the truth set + hap.py). Most hobby
   projects just produce output. This one produces output *and a measured accuracy score*.

2. **Everything is traceable and un-editable after the fact** (provenance stamps +
   insert-only database + versioned cloud storage). If someone asks "how exactly was this
   result produced six months ago?", we can answer precisely.

These two ideas are the whole reason the fancy words matter. The tools are just the means.

---

## How to actually try it (in plain terms)

You don't need to understand the code to see it work:

1. **Run the dependency-free demo** — the AI-summary and metrics parts run with just Python,
   no special software. See "dependency-free" in the [Glossary](GLOSSARY.md).
   ```bash
   # Ask the AI-style renderer to summarise an example result:
   python3 ai-report/infer.py --metrics <a-metrics.json-file> --offline
   ```
2. **Run the full pipeline** — needs **Nextflow** and **Docker** installed. This does the
   real DNA processing. See the [main README](../README.md) Quickstart.
3. **See the dashboard** — needs **Docker**. `docker compose up -d`, then open
   `http://localhost:3000`.

Start with #1 — it works immediately and shows the most human-readable output.

---

## Still confused by a word?

Every technical term in this project is in [GLOSSARY.md](GLOSSARY.md), grouped by topic
(DNA/sequencing, the pipeline tools, cloud/AWS, database, AI, and general software terms),
each with a one-line plain explanation and, where useful, an everyday analogy.
