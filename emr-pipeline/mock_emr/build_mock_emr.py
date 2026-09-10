#!/usr/bin/env python3
"""Build a tiny synthetic EMR database to stand in for an ODBC data source.

In a real ICU/Virtual ED (VVED) setting this data would live in the hospital's
EMR (e.g. an Oracle/SQL Server-backed system exposed to reporting tools via
ODBC). This script fabricates the same *shape* — two tables, `icu_admissions`
and `ed_consultations` — in a local SQLite file so the rest of `emr-pipeline/`
can be exercised end-to-end with no credentials, no network, and definitely no
real patient data.

Every row here is synthetic: fake names, fake MRNs prefixed `MOCK-`, and dates
anchored to 2026 so nothing could be mistaken for a real record.

    # production would use:
    #   import pyodbc
    #   conn = pyodbc.connect(
    #       "DRIVER={SQL Server};SERVER=emr-reporting.hospital.local;"
    #       "DATABASE=EMR_RPT;UID=svc_etl;PWD=***;"
    #   )
    # extract_and_load.py's `_connect()` is written so that swapping this
    # sqlite3.connect(...) call for the pyodbc one above is the only change
    # needed — the rest of the ETL (pandas transforms, provenance stamping,
    # insert-only load) is unchanged.

Usage:
    python emr-pipeline/mock_emr/build_mock_emr.py [--out PATH] [--force]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "mock_emr.db"

SCHEMA = """
CREATE TABLE icu_admissions (
    admission_id        TEXT PRIMARY KEY,
    mrn                  TEXT NOT NULL,          -- synthetic MRN, e.g. MOCK-0001
    patient_name         TEXT NOT NULL,          -- clearly fake, e.g. "TESTPATIENT, Alpha"
    age_years             INTEGER,
    sex                   TEXT,                   -- M/F/X
    admit_datetime        TEXT NOT NULL,          -- ISO 8601
    discharge_datetime    TEXT,                    -- NULL = still admitted
    unit                  TEXT NOT NULL,          -- ICU/HDU
    admission_source      TEXT,                    -- ED/Theatre/Ward/Retrieval
    primary_diagnosis     TEXT,
    diagnosis_icd10_am    TEXT,
    apache_ii_score       INTEGER,                 -- 0-71, synthetic severity proxy
    ventilated            INTEGER NOT NULL DEFAULT 0,  -- 0/1
    vasopressor_support   INTEGER NOT NULL DEFAULT 0,  -- 0/1
    outcome               TEXT                     -- discharged/died/transferred/NULL
);

CREATE TABLE ed_consultations (
    consult_id           TEXT PRIMARY KEY,
    mrn                  TEXT NOT NULL,
    patient_name         TEXT NOT NULL,
    consult_datetime      TEXT NOT NULL,
    referring_clinician   TEXT,
    consult_note          TEXT NOT NULL           -- free text, as a clinician typed it
);
"""

# 18 synthetic ICU admissions. One row (MOCK-0018) is deliberately incomplete
# (missing APACHE II + discharge) so downstream QC/validation code has a
# realistic missing-data case to catch, and one (MOCK-0011) has an
# out-of-range APACHE II score to exercise the ANZICS export's range checks.
ICU_ADMISSIONS = [
    ("ADM-0001", "MOCK-0001", "TESTPATIENT, Alpha", 64, "M", "2026-01-03T02:14:00", "2026-01-07T11:00:00", "ICU", "ED", "Septic shock", "A41.9", 22, 1, 1, "discharged"),
    ("ADM-0002", "MOCK-0002", "TESTPATIENT, Bravo", 71, "F", "2026-01-05T14:40:00", "2026-01-06T09:30:00", "ICU", "Theatre", "Post-op cardiac surgery", "Z98.8", 15, 1, 0, "discharged"),
    ("ADM-0003", "MOCK-0003", "TESTPATIENT, Charlie", 45, "M", "2026-01-08T22:05:00", "2026-01-10T08:00:00", "HDU", "Ward", "COPD exacerbation", "J44.1", 12, 0, 0, "discharged"),
    ("ADM-0004", "MOCK-0004", "TESTPATIENT, Delta", 58, "F", "2026-01-10T05:50:00", "2026-01-15T16:20:00", "ICU", "ED", "Diabetic ketoacidosis", "E10.1", 18, 0, 0, "discharged"),
    ("ADM-0005", "MOCK-0005", "TESTPATIENT, Echo", 80, "M", "2026-01-12T18:22:00", "2026-01-13T03:10:00", "ICU", "ED", "Cardiac arrest, ROSC", "I46.9", 34, 1, 1, "died"),
    ("ADM-0006", "MOCK-0006", "TESTPATIENT, Foxtrot", 39, "F", "2026-01-14T09:00:00", "2026-01-16T12:00:00", "ICU", "Retrieval", "Polytrauma", "T07", 20, 1, 1, "transferred"),
    ("ADM-0007", "MOCK-0007", "TESTPATIENT, Golf", 67, "M", "2026-01-16T13:35:00", "2026-01-19T10:15:00", "ICU", "ED", "Community-acquired pneumonia", "J18.9", 17, 1, 0, "discharged"),
    ("ADM-0008", "MOCK-0008", "TESTPATIENT, Hotel", 52, "F", "2026-01-18T01:12:00", "2026-01-20T07:45:00", "HDU", "Ward", "Upper GI bleed", "K92.2", 14, 0, 0, "discharged"),
    ("ADM-0009", "MOCK-0009", "TESTPATIENT, India", 29, "M", "2026-01-20T20:00:00", "2026-01-21T09:00:00", "ICU", "ED", "Status asthmaticus", "J46", 9, 1, 0, "discharged"),
    ("ADM-0010", "MOCK-0010", "TESTPATIENT, Juliet", 74, "F", "2026-01-22T04:44:00", "2026-01-29T15:00:00", "ICU", "Theatre", "Post-op AAA repair", "Z98.8", 25, 1, 1, "discharged"),
    ("ADM-0011", "MOCK-0011", "TESTPATIENT, Kilo", 61, "M", "2026-01-24T11:11:00", "2026-01-26T08:30:00", "ICU", "ED", "Severe sepsis", "A41.9", 90, 1, 1, "discharged"),  # APACHE II 90 is out of the 0-71 range on purpose
    ("ADM-0012", "MOCK-0012", "TESTPATIENT, Lima", 55, "F", "2026-01-25T16:30:00", "2026-01-27T09:00:00", "HDU", "Ward", "Acute pancreatitis", "K85.9", 11, 0, 0, "discharged"),
    ("ADM-0013", "MOCK-0013", "TESTPATIENT, Mike", 83, "M", "2026-01-27T07:00:00", "2026-01-28T19:45:00", "ICU", "ED", "Hypoxic respiratory failure", "J96.0", 28, 1, 1, "died"),
    ("ADM-0014", "MOCK-0014", "TESTPATIENT, November", 36, "F", "2026-01-29T02:30:00", "2026-01-30T10:00:00", "ICU", "Retrieval", "Traumatic brain injury", "S06.9", 19, 1, 0, "transferred"),
    ("ADM-0015", "MOCK-0015", "TESTPATIENT, Oscar", 48, "M", "2026-01-30T15:15:00", "2026-02-01T12:00:00", "ICU", "ED", "Necrotising fasciitis", "M72.6", 24, 1, 1, "discharged"),
    ("ADM-0016", "MOCK-0016", "TESTPATIENT, Papa", 69, "F", "2026-02-01T09:45:00", "2026-02-03T11:30:00", "HDU", "Ward", "Acute-on-chronic renal failure", "N17.9", 13, 0, 0, "discharged"),
    ("ADM-0017", "MOCK-0017", "TESTPATIENT, Quebec", 41, "M", "2026-02-02T21:20:00", "2026-02-04T06:00:00", "ICU", "ED", "Alcoholic ketoacidosis", "E87.2", 10, 0, 0, "discharged"),
    ("ADM-0018", "MOCK-0018", "TESTPATIENT, Romeo", 77, "F", "2026-02-04T03:00:00", None, "ICU", "ED", "Multi-organ failure", "R65.1", None, 1, 1, None),  # deliberately incomplete: still "admitted"
]

# 15 synthetic ED consultation free-text notes. Written in a rough clinical
# shorthand style so structure_consult_notes.py's rule-based offline
# extraction has realistic (if messy) text to parse.
ED_CONSULTATIONS = [
    ("CON-0001", "MOCK-0001", "TESTPATIENT, Alpha", "2026-01-03T01:50:00", "Dr. A. Nguyen", "64M p/w fever, hypotension BP 82/50, HR 118. Likely urosepsis. Started on IV fluids + broad spectrum abx. Discussed with ICU reg, for admission. High acuity."),
    ("CON-0002", "MOCK-0002", "TESTPATIENT, Bravo", "2026-01-05T14:10:00", "Dr. B. Singh", "71F, elective admission post CABG, routine post-op review. Stable obs. Admit to ICU for planned monitoring."),
    ("CON-0003", "MOCK-0003", "TESTPATIENT, Charlie", "2026-01-08T21:30:00", "Dr. C. Okafor", "45M known COPD, increased SOB and wheeze over 2 days, sats 88% RA. Nebulisers given, some improvement. For HDU admission, moderate acuity."),
    ("CON-0004", "MOCK-0004", "TESTPATIENT, Delta", "2026-01-10T05:20:00", "Dr. D. Lee", "58F GCS 14, glucose 32, ketones 5.8, pH 7.05. DKA. IV insulin infusion commenced. Admit ICU, high acuity."),
    ("CON-0005", "MOCK-0005", "TESTPATIENT, Echo", "2026-01-12T18:00:00", "Dr. E. Wallis", "80M out-of-hospital cardiac arrest, ROSC after 12 min CPR. Ventilated, on noradrenaline. Critical, admit ICU."),
    ("CON-0006", "MOCK-0006", "TESTPATIENT, Foxtrot", "2026-01-14T08:30:00", "Dr. F. Mensah", "39F MVA, multiple long bone fractures + suspected splenic injury. Hypotensive, activated massive transfusion. Retrieval to ICU, critical."),
    ("CON-0007", "MOCK-0007", "TESTPATIENT, Golf", "2026-01-16T13:00:00", "Dr. G. Patel", "67M productive cough, fever 39.1, CXR consolidation RLL. CURB-65 = 3. Admit ICU, high acuity, started abx."),
    ("CON-0008", "MOCK-0008", "TESTPATIENT, Hotel", "2026-01-18T00:45:00", "Dr. H. Ahmed", "52F haematemesis, Hb 78, tachycardic. 2 units PRBC given. For urgent endoscopy, admit HDU, moderate-high acuity."),
    ("CON-0009", "MOCK-0009", "TESTPATIENT, India", "2026-01-20T19:30:00", "Dr. I. Novak", "29M known asthmatic, severe exacerbation, unable to speak in full sentences, sats 90%. Nebs + IV magnesium given, some response. Admit ICU for close monitoring, high acuity."),
    ("CON-0010", "MOCK-0010", "TESTPATIENT, Juliet", "2026-01-22T04:20:00", "Dr. J. Brennan", "74F elective AAA repair, planned post-op ICU admission for haemodynamic monitoring. Stable."),
    ("CON-0011", "MOCK-0011", "TESTPATIENT, Kilo", "2026-01-24T10:50:00", "Dr. K. Osei", "61M fevers, rigors, lactate 4.2, BP 78/44 despite 2L fluids. Severe sepsis, source likely biliary. Admit ICU, critical, started noradrenaline."),
    ("CON-0012", "MOCK-0012", "TESTPATIENT, Lima", "2026-01-25T16:00:00", "Dr. L. Fischer", "55F epigastric pain radiating to back, lipase 1400. Acute pancreatitis, mild. Admit HDU, moderate acuity, IV fluids + analgesia."),
    ("CON-0013", "MOCK-0013", "TESTPATIENT, Mike", "2026-01-27T06:30:00", "Dr. M. Taylor", "83M progressive dyspnoea, sats 78% on room air, bibasal crackles. Type 1 respiratory failure. Intubated in ED, admit ICU, critical."),
    ("CON-0014", "MOCK-0014", "TESTPATIENT, November", "2026-01-29T02:00:00", "Dr. N. Carter", "36F fall from height, GCS 9, unequal pupils. Suspected TBI, CT pending. Retrieval to ICU, critical, intubated for airway protection."),
    ("CON-0015", "MOCK-0015", "TESTPATIENT, Oscar", "2026-01-30T14:45:00", "Dr. O. Reyes", "48M rapidly spreading leg erythema, pain out of proportion, febrile 39.6. Suspected necrotising fasciitis. Surgical review urgent, admit ICU, critical."),
]


def build(db_path: Path, force: bool = False) -> Path:
    if db_path.exists():
        if not force:
            print(f"{db_path} already exists (use --force to rebuild)")
            return db_path
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO icu_admissions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ICU_ADMISSIONS,
        )
        conn.executemany(
            "INSERT INTO ed_consultations VALUES (?,?,?,?,?,?)",
            ED_CONSULTATIONS,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"wrote {db_path} ({len(ICU_ADMISSIONS)} icu_admissions, "
          f"{len(ED_CONSULTATIONS)} ed_consultations)")
    return db_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_DB_PATH), help="output SQLite path")
    ap.add_argument("--force", action="store_true", help="overwrite an existing DB")
    args = ap.parse_args()
    build(Path(args.out), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
