# ⚠️ SYNTHETIC / MOCK PATIENT RECORD — FOR DEMO USE ONLY

> This is **fictional data** generated for a hackathon demonstration of the OR Assistant system.
> It does not describe any real person. Do not use for clinical decision-making.
> All names, identifiers, dates, and values are invented.

---

# Patient Record — Total Knee Arthroplasty (Right)

| Field | Value |
|---|---|
| Name | Margaret R. Donnelly |
| MRN | MOCK-4471920 |
| DOB | 14 Mar 1967 (Age 59) |
| Sex | Female |
| Height / Weight | 164 cm / 88 kg (BMI 32.7) |
| Blood group | O Rh-positive |
| Ward / Bed | Orthopaedics, Bed 12 |
| Admitting consultant | Mr. A. Vasquez (Orthopaedic Surgery) |
| Anaesthetist | Dr. P. Reuben |
| Planned procedure | Right total knee arthroplasty (TKA), cemented |
| Scheduled date | 11 Jun 2026, theatre list position 2 |
| ASA grade | III |

---

## 1. Presenting Diagnosis

**Severe tricompartmental osteoarthritis, right knee**, with failure of conservative management.

Primary indication for surgery: progressive right knee pain and functional decline over ~4 years, now limiting walking distance to under 100 m and disturbing sleep. Has failed physiotherapy, weight-management referral, NSAID trials, and two intra-articular corticosteroid injections (last injection 7 months ago, gave ~6 weeks of partial relief).

Oxford Knee Score: **18/48** (pre-op, indicating marked impairment).

---

## 2. History of Presenting Complaint

Right knee pain began insidiously ~4 years ago, initially activity-related, now present at rest and at night. Describes medial-sided pain, stiffness after inactivity ("gelling") lasting 20–30 minutes, and intermittent giving-way. Uses a single-point stick outdoors. No locking, no recent trauma. Left knee mildly symptomatic but not currently limiting (being managed conservatively).

---

## 3. Past Medical History

- **Type 2 diabetes mellitus** — diagnosed 2014, on oral agents. Most recent HbA1c **7.9%** (see labs) — *suboptimal control, relevant to infection and wound-healing risk.*
- **Hypertension** — diagnosed 2011, generally well controlled.
- **Chronic kidney disease, Stage 2–3a** — eGFR trending 58–62; attributed to diabetes/hypertension. *Relevant to renally-cleared drug dosing.*
- **Obstructive sleep apnoea** — uses home CPAP nightly; *relevant to peri-operative airway and post-op opioid sensitivity.*
- **Hypothyroidism** — on stable thyroxine replacement.
- **Obesity** — BMI 32.7.
- Previous **iron-deficiency anaemia**, treated; baseline Hb now low-normal (see labs).

---

## 4. Past Surgical & Anaesthetic History

- Laparoscopic cholecystectomy (2009) — uneventful.
- Diagnostic right knee arthroscopy (2021) — under general anaesthesia.
- **Post-operative nausea and vomiting (PONV)** noted after the 2021 arthroscopy despite ondansetron. *Flag for anaesthetic planning — consider multimodal antiemetic prophylaxis.*
- No personal or family history of malignant hyperthermia. No prior difficult intubation documented (Mallampati II at pre-assessment).

---

## 5. Allergies & Adverse Reactions ⚠️

| Agent | Reaction | Severity |
|---|---|---|
| **Penicillin** | Urticarial rash + facial swelling, age 30s | Moderate–severe — avoid beta-lactams unless specialist-cleared |
| **Adhesive dressings (acrylate)** | Contact dermatitis | Mild — use alternative dressing |
| Shellfish | GI upset only | Not a true allergy |

> **Demo-relevant flag:** The penicillin allergy directly affects **surgical antibiotic prophylaxis**. Standard cefazolin carries a small cross-reactivity consideration; the documented plan (Section 9) uses an alternative agent. This is a strong intra-OT query example: *"What's the antibiotic plan given her penicillin allergy?"*

---

## 6. Medications (Pre-admission)

| Drug | Dose | Notes for peri-op |
|---|---|---|
| Metformin | 1 g BD | Withhold morning of surgery; monitor renal function/glucose |
| Lisinopril | 10 mg OD | ACE inhibitor — anaesthetist to advise on day-of-surgery dose (hypotension risk) |
| Amlodipine | 5 mg OD | Continue |
| Levothyroxine | 100 mcg OD | Continue |
| Atorvastatin | 20 mg OD | Continue |
| **Aspirin 75 mg OD** | | Low-dose antiplatelet — *clarify indication; bleeding vs. thrombotic risk to be weighed. See Section 10.* |
| Paracetamol / topical NSAID | PRN | For knee pain |
| Vitamin D | 800 IU OD | Continue |

No anticoagulant (no DOAC, no warfarin). No insulin.

---

## 7. Social & Family History

- Retired schoolteacher. Lives with spouse in a two-storey house (stairs — relevant to discharge planning).
- Ex-smoker — quit 2015, ~15 pack-year history.
- Alcohol: 4–6 units/week.
- Independent in activities of daily living; mobility limited by the knee.
- Family history: mother had type 2 diabetes; father had ischaemic heart disease. No family history of bleeding disorders or anaesthetic complications.

---

## 8. Examination (Pre-operative)

**General:** Comfortable at rest. Overweight. No pallor or jaundice.

**Right knee:** Varus deformity ~8°, moderate effusion, medial joint-line tenderness, crepitus through range. Range of motion 5–95° (fixed flexion of 5°). Stable to varus/valgus and anteroposterior stress. Neurovascularly intact distally — dorsalis pedis and posterior tibial pulses palpable, sensation intact, good capillary refill.

**Cardiovascular:** Heart sounds normal, no murmurs. BP 138/84. No peripheral oedema.

**Respiratory:** Chest clear. SpO₂ 97% on air.

**Airway:** Mallampati II, good mouth opening, full neck extension.

---

## 9. Investigations

### 9.1 Laboratory (most recent, 09 Jun 2026)

| Test | Result | Reference | Flag |
|---|---|---|---|
| Haemoglobin | 11.4 g/dL | 12.0–15.5 | **Low** — borderline; consider pre-op optimisation, group & save done |
| White cell count | 7.2 ×10⁹/L | 4.0–11.0 | Normal |
| Platelets | 244 ×10⁹/L | 150–400 | Normal |
| Sodium | 139 mmol/L | 135–145 | Normal |
| Potassium | 4.6 mmol/L | 3.5–5.0 | Normal |
| Urea | 7.1 mmol/L | 2.5–7.8 | Normal |
| Creatinine | 102 µmol/L | 45–90 | **High** |
| eGFR | 58 mL/min/1.73m² | >90 | **Reduced** (CKD 3a) — affects drug dosing |
| HbA1c | 7.9% (63 mmol/mol) | <7.0% target | **Above target** — infection/healing risk |
| Fasting glucose | 8.4 mmol/L | 4.0–5.9 | **High** |
| CRP | 4 mg/L | <5 | Normal |
| Albumin | 38 g/L | 35–50 | Low-normal |
| TSH | 2.1 mU/L | 0.4–4.0 | Normal (treated) |
| INR | 1.0 | 0.8–1.1 | Normal |
| APTT | 31 s | 25–35 | Normal |
| Group & Save | O Rh-positive, antibody screen negative | | Valid; **no crossmatch ordered** — see Section 10 |

### 9.2 Imaging

- **Weight-bearing radiograph, right knee (AP + lateral), 02 Jun 2026:** Tricompartmental joint-space loss, most marked medially. Subchondral sclerosis, osteophytes, varus alignment. No fracture, no loose bodies. Findings consistent with end-stage osteoarthritis.
- **Long-leg alignment film:** Mechanical axis in varus; pre-operative templating performed.
- **Chest radiograph:** Clear; no acute changes.

### 9.3 Cardiac

- **ECG:** Sinus rhythm, rate 72, normal axis, no ischaemic changes, QTc normal.
- No echocardiogram indicated (good functional history pre-knee limitation, no cardiac symptoms).

---

## 10. Peri-operative Planning

### 10.1 Anaesthetic plan (Dr. Reuben)
- Planned **spinal anaesthesia** with light sedation (favoured given OSA and PONV history — reduces opioid load and airway risk).
- **PONV prophylaxis:** multimodal — dexamethasone + ondansetron, given prior PONV despite ondansetron alone.
- OSA: CPAP available in recovery; cautious opioid titration; extended post-op monitoring.
- Diabetes: variable-rate insulin infusion if glucose control deteriorates peri-operatively; metformin withheld morning of surgery.
- ACE inhibitor (lisinopril): omit on morning of surgery to reduce intra-operative hypotension.

### 10.2 Antibiotic prophylaxis ⚠️ (penicillin allergy)
- Standard first-line (cefazolin) **modified due to documented penicillin allergy.**
- **Planned agent: teicoplanin** (weight-adjusted) **+ gentamicin** (renally dosed for eGFR 58), per local policy for beta-lactam allergy. Gentamicin level monitoring per protocol given reduced renal function.
- *Strong demo query:* *"Confirm the prophylactic antibiotic and dose given her allergy and renal function."*

### 10.3 VTE prophylaxis
- High-risk procedure (major lower-limb arthroplasty) plus obesity and reduced mobility.
- Mechanical: intermittent pneumatic compression intra- and post-operatively.
- Pharmacological: low-molecular-weight heparin, **renally dose-adjusted** (eGFR 58), starting post-operatively per protocol.
- **Aspirin** to be reviewed — decision pending on whether to continue peri-operatively or substitute; documented as an open item for the team.

### 10.4 Blood management
- Hb borderline-low at 11.4 g/dL. Group & Save valid, antibody screen negative.
- Tranexamic acid planned intra-operatively (no contraindication) to reduce blood loss.
- Crossmatch not ordered pre-emptively; can convert from Save if needed. *Demo query: "Is blood crossmatched and what's the current Hb?"*

### 10.5 Glycaemic / metabolic
- Target peri-operative glucose 6–10 mmol/L.
- Hourly capillary glucose intra-operatively.

---

## 11. Surgical Plan & Implant Details

- **Procedure:** Right total knee arthroplasty, **cemented**, medial parapatellar approach.
- **Templated implant (pre-op planning):**
  - Femoral component: size 4 (cemented, cruciate-retaining)
  - Tibial component: size 3 (cemented)
  - Polyethylene insert: 10 mm starting trial
  - Patella: resurfacing planned (decision confirmed intra-operatively based on cartilage)
- **Alignment goal:** correct varus to neutral mechanical axis.
- **Tourniquet:** planned, with documented thigh pressure; intermittent release strategy considered given vascular/diabetic status.
- **Estimated blood loss anticipated:** moderate; TXA in use.
- Consent obtained and documented — risks discussed including infection, VTE, bleeding, stiffness, nerve/vessel injury, ongoing pain, and need for revision.

---

## 12. Progress / Pre-op Notes (chronological)

- **02 Jun 2026** — Pre-assessment clinic. Bloods, ECG, imaging reviewed. Flagged: HbA1c above target, borderline Hb, eGFR reduced, penicillin allergy, OSA, prior PONV. Optimisation discussed; patient counselled.
- **09 Jun 2026** — Repeat bloods (above). Group & Save sent. Fitness confirmed for surgery as ASA III.
- **10 Jun 2026** — Admitted. Consent re-confirmed. Anaesthetic review by Dr. Reuben; spinal plan agreed. CPAP brought in. Medication plan documented (withhold metformin and lisinopril am of surgery).
- **11 Jun 2026 (planned)** — Theatre, list position 2. WHO checklist to be completed; allergy and antibiotic plan to be verbally confirmed at sign-in and time-out.

---

## 13. Quick-Reference Summary (for intra-OT surfacing)

> **59F, right cemented TKA, ASA III.**
> **Allergy: PENICILLIN** (rash + swelling) → prophylaxis = teicoplanin + renally-dosed gentamicin.
> **T2DM** HbA1c 7.9%, glucose target 6–10. Metformin withheld.
> **CKD 3a** eGFR 58 → renally dose gentamicin & LMWH.
> **OSA** on CPAP → cautious opioids, spinal preferred.
> **Hb 11.4 (low-normal)**, Group & Save valid (O Rh+), TXA planned, no crossmatch.
> **Prior PONV** → multimodal antiemetic prophylaxis.
> **On aspirin 75 mg** — peri-op continuation under review.
> Implant: femur size 4, tibia size 3, 10 mm insert, patella resurfacing planned.

---

*End of synthetic record. Generated for OR Assistant demo — not a real patient.*
