# I-589 Asylum Application - Ground Truth Analysis

**Form**: I-589 Application for Asylum and for Withholding of Removal
**Edition**: 01/20/25
**Pages**: 12
**OMB Number**: 1615-0067
**Analysis Date**: October 25, 2025

---

## Form Metadata

- **Form Title**: Application for Asylum and for Withholding of Removal
- **Agency**: Department of Homeland Security, U.S. Citizenship and Immigration Services
- **Total Pages**: 12 (main form) + 2 supplements
- **Expiration**: 09/30/2027
- **Instructions**: "Type or print in black ink"
- **Requirement**: "You must be residing in the United States to submit this form"

---

## High-Level Structure

### Main Sections (Parts A-G)
1. **Part A.I** - Information About You (Page 1)
2. **Part A.II** - Information About Your Spouse and Children (Pages 2-3)
3. **Part A.III** - Information About Your Background (Page 4)
4. **Part B** - Information About Your Application (Pages 5-6)
5. **Part C** - Additional Information About Your Application (Pages 7-8)
6. **Part D** - Your Signature (Page 9)
7. **Part E** - Declaration of Person Preparing Form (Page 9)
8. **Part F** - To Be Completed at Asylum Interview (Page 10)
9. **Part G** - To Be Completed at Removal Hearing (Page 10)

### Supplemental Forms
- **Supplement A** - Additional Children (Page 11)
- **Supplement B** - Additional Information/Continuation (Page 12)

---

## Part A.I: Information About You

**Page**: 1
**Field Count**: 25 fields

### Fields

| # | Label | Field Type | Validation | Optional | Notes |
|---|-------|------------|------------|----------|-------|
| 1 | Alien Registration Number(s) (A-Number) | text | A-number format | Yes | "(if any)" |
| 2 | U.S. Social Security Number | text | SSN format | Yes | "(if any)" |
| 3 | USCIS Online Account Number | text | Account number format | Yes | "(if any)" |
| 4 | Complete Last Name | text | Required | No | |
| 5 | First Name | text | Required | No | |
| 6 | Middle Name | text | | Yes | |
| 7 | What other names have you used | textarea | | Yes | "(include maiden name and aliases)" |
| 8 | Residence in the U.S. (where you physically reside) | address_group | Required | No | Multi-part |
| 8a | Street Number and Name | text | Required | No | |
| 8b | Apt. Number | text | | Yes | |
| 8c | City | text | Required | No | |
| 8d | State | select | US states | No | |
| 8e | Zip Code | text | 5-digit ZIP | No | |
| 8f | Telephone Number | tel | Phone format | No | Format: (___) ___ - ____ |
| 9 | Mailing Address in the U.S. | address_group | | Yes | "(if different than the address in Item Number 8)" |
| 9a | In Care Of | text | | Yes | "(if applicable)" |
| 9b | Street Number and Name | text | | Yes | |
| 9c | Apt. Number | text | | Yes | |
| 9d | City | text | | Yes | |
| 9e | State | select | US states | Yes | |
| 9f | Zip Code | text | 5-digit ZIP | Yes | |
| 9g | Telephone Number | tel | Phone format | Yes | Format: (___) ___ - ____ |
| 10 | Sex | radio | Male/Female | No | 2 options |
| 11 | Marital Status | radio | 4 options | No | Single, Married, Divorced, Widowed |
| 12 | Date of Birth | date | mm/dd/yyyy | No | Past date only |
| 13 | City and Country of Birth | text | | No | |
| 14 | Present Nationality (Citizenship) | text | | No | |
| 15 | Nationality at Birth | text | | No | |
| 16 | Race, Ethnic, or Tribal Group | text | | No | |
| 17 | Religion | text | | No | |
| 18 | Check the box, a through c, that applies | radio | 3 options | No | Immigration Court status |
| 18a | I have never been in Immigration Court proceedings | checkbox | | No | Mutually exclusive with b, c |
| 18b | I am now in Immigration Court proceedings | checkbox | | No | Mutually exclusive with a, c |
| 18c | I am not now in Immigration Court proceedings, but I have been in the past | checkbox | | No | Mutually exclusive with a, b |
| 19 | Complete 19 a through c | group | | No | Entry information |
| 19a | When did you last leave your country? | date | mm/dd/yyyy | No | |
| 19b | What is your current I-94 Number, if any? | text | | Yes | |
| 19c | List each entry into the U.S. | table | | No | Multi-entry, repeating rows |
| 19c-Date | Date | date | mm/dd/yyyy | No | Repeating |
| 19c-Place | Place | text | | No | Repeating |
| 19c-Status | Status | text | | No | Repeating |
| 19c-DateStatusExpires | Date Status Expires | date | mm/dd/yyyy | Yes | Only on first row |
| 20 | What country issued your last passport or travel document? | text | | No | |
| 21 | Passport Number / Travel Document Number | text | | No | Two separate fields |
| 22 | Expiration Date | date | mm/dd/yyyy | No | Future date |
| 23 | What is your native language | text | | No | "(include dialect, if applicable)" |
| 24 | Are you fluent in English? | radio | Yes/No | No | |
| 25 | What other languages do you speak fluently? | text | | Yes | |
| NOTE | Convention Against Torture checkbox | checkbox | | Yes | Top of form |

### Special Characteristics - Part A.I

**Conditional Logic**:
- Field 9 (Mailing Address) - Only required if different from Field 8
- Field 18 - Only one of a, b, c can be selected
- Field 19c - Variable number of entries (note says "Attach additional sheets as needed")

**Multi-Entry Fields**:
- 19c: U.S. entry history (3 rows provided, expandable)

**Format Constraints**:
- Dates: mm/dd/yyyy format
- Phone: (___) ___ - ____ format with parentheses
- ZIP Code: 5 digits

---

## Part A.II: Information About Your Spouse and Children

**Pages**: 2-3
**Field Count**: Spouse (24 fields) + Children (4 × 21 fields = 84 fields)

### Spouse Section (Page 2)

| # | Label | Field Type | Validation | Optional | Notes |
|---|-------|------------|------------|----------|-------|
| - | I am not married | checkbox | | Yes | Skip to children if checked |
| 1 | Alien Registration Number (A-Number) | text | A-number format | Yes | "(if any)" |
| 2 | Passport/ID Card Number | text | | Yes | "(if any)" |
| 3 | Date of Birth | date | mm/dd/yyyy | No | |
| 4 | U.S. Social Security Number | text | SSN format | Yes | "(if any)" |
| 5 | Complete Last Name | text | Required | No | |
| 6 | First Name | text | Required | No | |
| 7 | Middle Name | text | | Yes | |
| 8 | Other names used | text | | Yes | "(include maiden name and aliases)" |
| 9 | Date of Marriage | date | mm/dd/yyyy | No | |
| 10 | Place of Marriage | text | | No | |
| 11 | City and Country of Birth | text | | No | |
| 12 | Nationality (Citizenship) | text | | No | |
| 13 | Race, Ethnic, or Tribal Group | text | | No | |
| 14 | Sex | radio | Male/Female | No | |
| 15 | Is this person in the U.S.? | radio | Yes/No | No | Triggers conditional fields |
| 16 | Place of last entry into the U.S. | text | | Conditional | If in U.S. |
| 17 | Date of last entry into the U.S. | date | mm/dd/yyyy | Conditional | If in U.S. |
| 18 | I-94 Number | text | | Conditional | If in U.S., "(if any)" |
| 19 | Status when last admitted (Visa type, if any) | text | | Conditional | If in U.S. |
| 20 | What is your spouse's current status? | text | | Conditional | If in U.S. |
| 21 | What is the expiration date of his/her authorized stay, if any? | date | mm/dd/yyyy | Conditional | If in U.S. |
| 22 | Is your spouse in Immigration Court proceedings? | radio | Yes/No | Conditional | If in U.S. |
| 23 | If previously in the U.S., date of previous arrival | date | mm/dd/yyyy | Conditional | If NOT in U.S. |
| 24 | If in the U.S., is your spouse to be included in this application? | radio | Yes/No | Conditional | If in U.S. |
| - | No (Specify location) | text | | Conditional | If NOT in U.S. |

### Children Section (Pages 2-3)

**Header**: "Your Children. List all of your children, regardless of age, location, or marital status."

**Options**:
- "I do not have any children" checkbox - Skip section if checked
- "I have children. Total number of children: ___" - Fill in number and complete entries

**Provided Slots**: 4 children (Page 2: 1 child, Page 3: 3 children)

**Overflow**: "Use Form I-589 Supplement A or attach additional sheets of paper and documentation if you have more than four children."

**Per-Child Fields** (21 fields each):

| # | Label | Field Type | Validation | Optional | Notes |
|---|-------|------------|------------|----------|-------|
| 1 | Alien Registration Number (A-Number) | text | A-number format | Yes | "(if any)" |
| 2 | Passport/ID Card Number | text | | Yes | "(if any)" |
| 3 | Marital Status | select | 4 options | No | Married, Single, Divorced, Widowed |
| 4 | U.S. Social Security Number | text | SSN format | Yes | "(if any)" |
| 5 | Complete Last Name | text | Required | No | |
| 6 | First Name | text | Required | No | |
| 7 | Middle Name | text | | Yes | |
| 8 | Date of Birth | date | mm/dd/yyyy | No | |
| 9 | City and Country of Birth | text | | No | |
| 10 | Nationality (Citizenship) | text | | No | |
| 11 | Race, Ethnic, or Tribal Group | text | | No | |
| 12 | Sex | radio | Male/Female | No | |
| 13 | Is this child in the U.S.? | radio | Yes/No | No | Triggers conditional |
| 14 | Place of last entry into the U.S. | text | | Conditional | If in U.S. |
| 15 | Date of last entry into the U.S. | date | mm/dd/yyyy | Conditional | If in U.S. |
| 16 | I-94 Number | text | | Conditional | If in U.S., "(if any)" |
| 17 | Status when last admitted (Visa type, if any) | text | | Conditional | If in U.S. |
| 18 | What is your child's current status? | text | | Conditional | If in U.S. |
| 19 | What is the expiration date of his/her authorized stay, if any? | date | mm/dd/yyyy | Conditional | If in U.S. |
| 20 | Is your child in Immigration Court proceedings? | radio | Yes/No | Conditional | If in U.S. |
| 21 | If in the U.S., is this child to be included in this application? | radio | Yes/No | Conditional | If in U.S. |
| - | No (Specify location) | text | | Conditional | If NOT in U.S. |

### Special Characteristics - Part A.II

**Conditional Logic**:
- Spouse: Field 15 ("Is this person in the U.S.?") controls visibility of fields 16-24
- Children: Field 13 ("Is this child in the U.S.?") controls visibility of fields 14-21
- "Specify location" appears only if person is NOT in U.S.

**Multi-Entry Pattern**:
- Spouse: 0 or 1 entry (skip if not married)
- Children: 0 to unlimited entries (4 provided, expandable via Supplement A)

**Repeating Structure**:
- Children section repeats identical 21-field structure for each child
- Page 3 shows 3 additional identical child blocks

---

## Part A.III: Information About Your Background

**Page**: 4
**Section Count**: 5 tables

### Section 1: Last Address Before Coming to U.S.

**Instruction**: "List your last address where you lived before coming to the United States. If this is not the country where you fear persecution, also list the last address in the country where you fear persecution."

**Table Structure**: Variable rows (note: "Use Form I-589 Supplement B, or additional sheets of paper, if necessary")

| Column | Field Type | Label | Validation |
|--------|------------|-------|------------|
| 1 | text | Number and Street (Provide if available) | Optional |
| 2 | text | City/Town | Required |
| 3 | text | Department, Province, or State | Required |
| 4 | text | Country | Required |
| 5 | text | Dates From (Mo/Yr) | Date format Mo/Yr |
| 6 | text | Dates To (Mo/Yr) | Date format Mo/Yr |

**Rows Provided**: 2
**Expandable**: Yes

### Section 2: Residences During Past 5 Years

**Instruction**: "Provide the following information about your residences during the past 5 years. List your present address first."

**Table Structure**: Same as Section 1

| Column | Field Type | Label | Validation |
|--------|------------|-------|------------|
| 1 | text | Number and Street | Optional |
| 2 | text | City/Town | Required |
| 3 | text | Department, Province, or State | Required |
| 4 | text | Country | Required |
| 5 | text | Dates From (Mo/Yr) | Date format Mo/Yr |
| 6 | text | Dates To (Mo/Yr) | Date format Mo/Yr |

**Rows Provided**: 5
**Expandable**: Yes

### Section 3: Education History

**Instruction**: "Provide the following information about your education, beginning with the most recent school that you attended."

**Table Structure**:

| Column | Field Type | Label | Validation |
|--------|------------|-------|------------|
| 1 | text | Name of School | Required |
| 2 | text | Type of School | Required |
| 3 | text | Location (Address) | Required |
| 4 | text | Attended From (Mo/Yr) | Date format Mo/Yr |
| 5 | text | Attended To (Mo/Yr) | Date format Mo/Yr |

**Rows Provided**: 3
**Expandable**: Yes

### Section 4: Employment During Past 5 Years

**Instruction**: "Provide the following information about your employment during the past 5 years. List your present employment first."

**Table Structure**:

| Column | Field Type | Label | Validation |
|--------|------------|-------|------------|
| 1 | text | Name and Address of Employer | Required |
| 2 | text | Your Occupation | Required |
| 3 | text | Dates From (Mo/Yr) | Date format Mo/Yr |
| 4 | text | Dates To (Mo/Yr) | Date format Mo/Yr |

**Rows Provided**: 4
**Expandable**: Yes

### Section 5: Parents and Siblings

**Instruction**: "Provide the following information about your parents and siblings (brothers and sisters). Check the box if the person is deceased."

**Table Structure**:

| Column | Field Type | Label | Validation |
|--------|------------|-------|------------|
| 1 | text | Full Name | Required |
| 2 | text | City/Town and Country of Birth | Required |
| 3 | text | Current Location | Required |
| 4 | checkbox | Deceased | Optional |

**Rows Provided**:
- Mother: 1 row
- Father: 1 row
- Sibling: 4 rows

**Row Labels**: Pre-filled ("Mother", "Father", "Sibling" × 4)
**Expandable**: Yes

### Special Characteristics - Part A.III

**Date Format**: Mo/Yr (not full mm/dd/yyyy like other sections)

**Multi-Entry Tables**: All 5 sections support variable rows with expansion via Supplement B

**Deceased Checkbox**: Only in Section 5 (Parents and Siblings)

**Ordering Requirements**:
- Section 2: "List your present address first" (reverse chronological)
- Section 3: "beginning with the most recent school" (reverse chronological)
- Section 4: "List your present employment first" (reverse chronological)

---

## Part B: Information About Your Application

**Pages**: 5-6
**Purpose**: Core asylum claim narrative

### Question 1: Basis for Asylum Claim (Page 5)

**Label**: "Why are you applying for asylum or withholding of removal under section 241(b)(3) of the INA, or for withholding of removal under the Convention Against Torture?"

**Sub-label**: "I am seeking asylum or withholding of removal based on:"

**Checkboxes** (multi-select allowed):
- Race
- Religion
- Nationality
- Political opinion
- Membership in a particular social group
- Torture Convention

**Sub-Question 1A**: "Have you, your family, or close friends or colleagues ever experienced harm or mistreatment or threats in the past by anyone?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea with structured prompt:
  1. What happened;
  2. When the harm or mistreatment or threats occurred;
  3. Who caused the harm or mistreatment or threats; and
  4. Why you believe the harm or mistreatment or threats occurred.

**Sub-Question 1B**: "Do you fear harm or mistreatment if you return to your home country?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea with structured prompt:
  1. What harm or mistreatment you fear;
  2. Who you believe would harm or mistreat you; and
  3. Why you believe you would or could be harmed or mistreated.

### Question 2: Arrest/Detention History (Page 6)

**Label**: "Have you or your family members ever been accused, charged, arrested, detained, interrogated, convicted and sentenced, or imprisoned in any country other than the United States (including for an immigration law violation)?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "explain the circumstances and reasons for the action"

### Question 3A: Organizational Membership (Page 6)

**Label**: "Have you or your family members ever belonged to or been associated with any organizations or groups in your home country, such as, but not limited to, a political party, student group, labor union, religious organization, military or paramilitary group, civil patrol, guerrilla organization, ethnic group, human rights group, or the press or media?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "describe for each person the level of participation, any leadership or other positions held, and the length of time you or your family members were involved in each organization or activity"

### Question 3B: Current Participation (Page 6)

**Label**: "Do you or your family members continue to participate in any way in these organizations or groups?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "describe for each person your or your family members' current level of participation, any leadership or other positions currently held, and the length of time you or your family members have been involved in each organization or group"

### Question 4: Fear of Torture (Page 6)

**Label**: "Are you afraid of being subjected to torture in your home country or any other country to which you may be returned?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "explain why you are afraid and describe the nature of torture you fear, by whom, and why it would be inflicted"

### Special Characteristics - Part B

**Large Textareas**: All "If Yes" responses use large text boxes (approximately 1/2 page each)

**Structured Prompts**: Questions 1A and 1B provide numbered sub-prompts to guide responses

**Overflow**: Top of page 5 note: "Use Form I-589 Supplement B, or attach additional sheets of paper as needed to complete your responses"

**Multi-Select**: Question 1 checkboxes allow selecting multiple bases for asylum

---

## Part C: Additional Information About Your Application

**Pages**: 7-8
**Purpose**: Travel history, prior applications, and criminal history

### Question 1: Prior Asylum Applications (Page 7)

**Label**: "Have you, your spouse, your child(ren), your parents or your siblings ever applied to the U.S. Government for refugee status, asylum, or withholding of removal?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea with detailed instructions about explaining:
  - The decision and outcome
  - Status received
  - Whether included in parent/spouse application
  - Parent/spouse A-number if applicable
  - If denied by immigration judge or BIA: changes in country conditions or personal circumstances since denial

### Question 2A: Travel Through Other Countries (Page 7)

**Label**: "After leaving the country from which you are claiming asylum, did you or your spouse or child(ren) who are now in the United States travel through or reside in any other country before entering the United States?"

- **Type**: radio (Yes/No)

### Question 2B: Lawful Status in Other Countries (Page 7)

**Label**: "Have you, your spouse, your child(ren), or other family members, such as your parents or siblings, ever applied for or received any lawful status in any country other than the one from which you are now claiming asylum?"

- **Type**: radio (Yes/No)

**If Yes to 2A and/or 2B**: Large textarea - "provide for each person the following: the name of each country and the length of stay, the person's status while there, the reasons for leaving, whether or not the person is entitled to return for lawful residence purposes, and whether the person applied for refugee status or for asylum while there, and if not, why he or she did not do so."

### Question 3: Persecution of Others (Page 7)

**Label**: "Have you, your spouse or your child(ren) ever ordered, incited, assisted or otherwise participated in causing harm or suffering to any person because of his or her race, religion, nationality, membership in a particular social group or belief in a particular political opinion?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "describe in detail each such incident and your own, your spouse's, or your child(ren)'s involvement"

### Question 4: Return to Country of Persecution (Page 8)

**Label**: "After you left the country where you were harmed or fear harm, did you return to that country?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "describe in detail the circumstances of your visit(s) (for example, the date(s) of the trip(s), the purpose(s) of the trip(s), and the length of time you remained in that country for the visit(s).)"

### Question 5: One-Year Filing Deadline (Page 8)

**Label**: "Are you filing this application more than 1 year after your last arrival in the United States?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea with detailed instruction: "explain why you did not file within the first year after you arrived. You must be prepared to explain at your interview or hearing why you did not file your asylum application within the first year after you arrived. For guidance in answering this question, see Instructions, Part 1: Filing Instructions, Section V. 'Completing the Form,' Part C."

### Question 6: U.S. Criminal History (Page 8)

**Label**: "Have you or any member of your family included in the application ever committed any crime and/or been arrested, charged, convicted, or sentenced for any crimes in the United States (including for an immigration law violation)?"

- **Type**: radio (Yes/No)
- **If Yes**: Large textarea - "for each instance, specify in your response: what occurred and the circumstances, dates, length of sentence received, location, the duration of the detention or imprisonment, reason(s) for the detention or conviction, any formal charges that were lodged against you or your relatives included in your application, and the reason(s) for release. Attach documents referring to these incidents, if they are available, or an explanation of why documents are not available."

### Special Characteristics - Part C

**Continuation Note**: Top of page 7: "Use Form I-589 Supplement B, or attach additional sheets of paper as needed to complete your responses to the questions contained in Part C."

**Compound Questions**: 2A and 2B are separate Yes/No, but share single textarea if either is Yes

**Legal Significance**: Several questions have legal implications (persecution of others, criminal history, one-year deadline)

---

## Part D: Your Signature

**Page**: 9
**Purpose**: Applicant certification and signature

### Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Print your complete name | text | Yes | |
| Write your name in your native alphabet | text | Yes | Separate box |
| Daytime Telephone Number | tel | Yes | |
| Did your spouse, parent, or child(ren) assist you in completing this application? | radio | Yes | Yes/No |
| (If Yes) Name and Relationship | text (2 sets) | Conditional | Two name/relationship pairs |
| Did someone other than your spouse, parent, or child(ren) prepare this application? | radio | Yes | Yes/No, triggers Part E |
| Have you been provided with a list of persons who may be available to assist you? | radio | Yes | Yes/No |
| Signature of Applicant | signature | Yes | "Sign your name so it all appears within the brackets" |
| Date | date | Yes | mm/dd/yyyy |

### Certification Text

Large block of legal text including:
- Penalty of perjury statement
- 18 USC 1546(a) reference (up to 25 years imprisonment for false statements)
- Physical presence certification
- Authorization to release immigration records

### Warning Text

Large WARNING block about:
- Removal proceedings if asylum denied
- Frivolous application consequences (permanent ineligibility)
- Biometrics appointment requirements
- References to INA sections and CFR regulations

---

## Part E: Declaration of Person Preparing Form

**Page**: 9
**Purpose**: Preparer certification (if someone helped)

**Condition**: Only complete if answered "Yes" to Part D preparer question

### Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Signature of Preparer | signature | Yes | |
| Print Complete Name of Preparer | text | Yes | |
| Daytime Telephone Number | tel | Yes | (___) format |
| Address of Preparer: Street Number and Name | text | Yes | |
| Apt. Number | text | No | |
| City | text | Yes | |
| State | select | Yes | |
| Zip Code | text | Yes | |
| Attorney or Accredited Representative (To be completed by attorney/rep if any) | group | No | Optional section |
| Select this box if Form G-28 is attached | checkbox | No | |
| Attorney State Bar Number (if applicable) | text | No | |
| Attorney or Accredited Representative USCIS Online Account Number (if any) | text | No | |

### Declaration Text

Certification that preparer:
- Prepared at applicant's request
- Responses based on information provided by applicant
- Read to applicant in native language before signature
- Aware of civil penalties (8 USC 1324c) and criminal penalties (18 USC 1546(a))

---

## Part F: To Be Completed at Asylum Interview

**Page**: 10
**Purpose**: Asylum officer completion

### Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| I swear (affirm) that I know the contents... | checkbox | Yes | "all true" or "not all true" |
| correction(s) numbered ___ to ___ were made by me or at my request | text (2 fields) | Conditional | If corrections made |
| Signature of Applicant | signature | Yes | |
| Write Your Name in Your Native Alphabet | text | Yes | |
| Date | date | Yes | mm/dd/yyyy |
| Signature of Asylum Officer | signature | Yes | Officer completes |

### Certification Text

Includes:
- Statement of truth
- Frivolous application warning
- Cannot avoid frivolous finding even if advised by someone else

---

## Part G: To Be Completed at Removal Hearing

**Page**: 10
**Purpose**: Immigration judge completion

### Structure

**Identical to Part F**, but for immigration judge context

### Fields

Same 6 fields as Part F:
- Truth certification checkbox
- Corrections numbered fields
- Applicant signature
- Native alphabet name
- Date
- Immigration Judge signature (instead of Asylum Officer)

---

## Supplement A: Additional Children

**Page**: 11
**Purpose**: Overflow for more than 4 children

### Header Fields

| Field | Type | Required |
|-------|------|----------|
| A-Number (If available) | text | No |
| Date | date | Yes |
| Applicant's Name | text | Yes |
| Applicant's Signature | signature | Yes |

### Children Entries

**Title**: "List All of Your Children, Regardless of Age or Marital Status"

**Note**: "Use this form and attach additional pages and documentation as needed, if you have more than four children"

**Rows Provided**: 2 child entries per page

**Per-Child Fields**: Identical 21-field structure from Part A.II (see above)

---

## Supplement B: Additional Information

**Page**: 12
**Purpose**: Continuation page for any question

### Header Fields

| Field | Type | Required |
|-------|------|----------|
| A-Number (if available) | text | No |
| Date | date | Yes |
| Applicant's Name | text | Yes |
| Applicant's Signature | signature | Yes |

### Content Fields

| Field | Type | Notes |
|-------|------|-------|
| Part | text | Which part being continued |
| Question | text | Which question being continued |
| (Large blank area) | textarea | Full page for response |

**Note**: "Use this as a continuation page for any additional information requested. Copy and complete as needed."

---

## Field Type Summary

### Field Type Inventory

| Field Type | Count (Approx) | Examples |
|------------|----------------|----------|
| **text** | 120+ | Names, addresses, A-numbers, passport numbers |
| **textarea** | 15+ | Part B narrative questions, Part C explanations |
| **date** | 35+ | Birth dates, entry dates, marriage dates |
| **radio** | 25+ | Yes/No questions, Sex, Marital Status |
| **checkbox** | 15+ | Immigration court status, basis for asylum, deceased |
| **select** | 5+ | State dropdowns, marital status (children) |
| **tel** | 5+ | Phone numbers with (___) ___ - ____ format |
| **signature** | 6 | Applicant, preparer, officers |
| **address_group** | 3 | Residence, mailing address, preparer address |
| **table** | 5+ | Children, residences, education, employment, family |

### Validation Rules Identified

1. **Date Formats**:
   - Full date: mm/dd/yyyy (birthdate, entry dates)
   - Month/Year only: Mo/Yr (employment, education, residences 5-year history)

2. **Phone Format**: (___) ___ - ____ with parentheses and spaces

3. **Optional vs Required**:
   - "(if any)" notation indicates optional
   - Lack of notation generally means required
   - Conditional fields depend on parent answer

4. **Conditional Display**:
   - "Complete Blocks X to Y" - shown only if condition met
   - "If Yes, explain..." - textarea shown conditionally
   - "Is person in U.S.?" controls visibility of 8-10 follow-up fields

5. **Multi-Entry Constraints**:
   - Variable-length tables with "attach additional sheets as needed"
   - Pre-allocated rows (e.g., 3 U.S. entries, 4 children, 5 residences)
   - Overflow via Supplement A (children) or Supplement B (everything else)

---

## Special Patterns and Edge Cases

### 1. Mutually Exclusive Groups

**Field 18** (Immigration Court proceedings):
- Only one of a, b, c can be selected
- Appears as three separate checkboxes but functions as radio group

### 2. Conditional Cascades

**Spouse and Children** "In U.S.?" triggers:
- If Yes: Complete blocks 14-21 (8-10 fields)
- If No: Show "Specify location" text field instead

### 3. Shared Textareas

**Part C, Questions 2A and 2B**:
- Two separate Yes/No questions
- Single shared textarea if EITHER is Yes
- Prompt instructs to address both if both are Yes

### 4. Variable Table Rows

All background tables can expand:
- Initial rows provided (2-5 depending on section)
- Note: "attach additional sheets" or "Use Form I-589 Supplement B"
- No explicit maximum stated

### 5. Date Range Validation

- Birth dates: must be past
- Passport expiration: should be future (but may be expired for asylum applicants)
- Employment/residence dates: From date should be ≤ To date
- "Last 5 years" constraint on residences and employment

### 6. Multi-Select Checkboxes

**Part B, Question 1** (basis for asylum):
- Six checkboxes (Race, Religion, Nationality, Political opinion, Social group, Torture)
- Multiple selections allowed
- At least one should be selected

### 7. Signature Fields

Three contexts:
- **Applicant**: Standard signature line
- **Preparer**: Standard signature line (if applicable)
- **Officials**: Signature with title (Asylum Officer, Immigration Judge)

Special instruction: "Sign your name so it all appears within the brackets" with visual brackets [ ]

### 8. Native Alphabet Field

Appears 3 times:
- Part D (applicant signature)
- Part F (asylum interview)
- Part G (removal hearing)

Purpose: Non-Latin alphabet representation of name

### 9. Bi-lingual Name Support

Multiple name fields:
- Legal name (Last, First, Middle)
- Other names used (aliases, maiden name)
- Native alphabet name
- Spouse's other names
- Children's names (repeated)

### 10. Repeating Structures

**Identical sub-forms**:
- Children: Exact same 21 fields repeated 4+ times
- Siblings: Same fields repeated 4+ times
- U.S. entries: Same 3-4 fields repeated 3+ times

---

## Form Flow and Logic

### User Journey

1. **Part A.I**: Basic identity and entry information → All users
2. **Part A.II**: Family information → Skip spouse if unmarried, skip children if none
3. **Part A.III**: Background → All users (tables can be sparse)
4. **Part B**: Core asylum narrative → All users, most critical section
5. **Part C**: Additional disclosures → All users, some may answer "No" to all
6. **Part D**: Signature → All users
7. **Part E**: Preparer info → Only if someone helped
8. **Parts F/G**: Government use only → Completed during adjudication
9. **Supplements**: As needed for overflow

### Section Dependencies

- Part A.II (spouse) depends on marital status
- Part A.II (children) depends on having children
- Part E depends on Part D preparer question
- Supplement A triggered by >4 children
- Supplement B triggered by insufficient space in any textarea

### Required vs Optional Sections

**Always Required**:
- Part A.I (Information About You)
- Part A.III (Background) - though some tables may be sparse
- Part B (Application basis)
- Part D (Signature)

**Conditionally Required**:
- Part A.II Spouse - if married
- Part A.II Children - if have children
- Part C responses - only "If Yes" textareas
- Part E - only if someone prepared form

**Government Use Only**:
- Parts F and G

---

## Validation and Error Handling Implications

### Client-Side Validation Opportunities

1. **Format Validation**:
   - Date format: mm/dd/yyyy or Mo/Yr
   - Phone format: (XXX) XXX-XXXX
   - ZIP code: 5 digits
   - Email: standard format (if added to schema)

2. **Range Validation**:
   - Birth date: must be past, reasonable range (1900-present)
   - Passport expiration: flag if already expired (warning, not error)
   - Date ranges: From ≤ To
   - "Last 5 years": From date ≥ (current year - 5)

3. **Conditional Required**:
   - If "In U.S.?" = Yes, then fields 14-21 required
   - If Question = "Yes", then textarea required
   - If married, then spouse fields required

4. **Logical Consistency**:
   - If "I am not married" checked, skip spouse section
   - If "no children" checked, skip children section
   - If field 18a checked, 18b and 18c must be unchecked

5. **Multi-Entry Validation**:
   - At least one U.S. entry required
   - If "Total number of children: X", then X child records should be present
   - Table rows: From/To dates should not overlap

### Server-Side Validation Requirements

1. **Signature Presence**: Ensure signature captured (not empty)
2. **Truth Certification**: Part D checkboxes acknowledged
3. **Frivolous Application Check**: Flag patterns indicating fraudulent claim
4. **Document Attachment**: Verify referenced documents attached
5. **Supplement Consistency**: Cross-check main form and supplements

---

## PDF Fillable Field Names (Inferred)

Based on visual structure, likely field names in fillable PDF:

### Part A.I
```
a1_anumber
a1_ssn
a1_uscis_account
a1_lastname
a1_firstname
a1_middlename
a1_othername
a1_residence_street
a1_residence_apt
a1_residence_city
a1_residence_state
a1_residence_zip
a1_residence_phone
a1_mailing_incareof
a1_mailing_street
a1_mailing_apt
a1_mailing_city
a1_mailing_state
a1_mailing_zip
a1_mailing_phone
a1_sex (radio: male/female)
a1_marital_status (radio: single/married/divorced/widowed)
a1_dob
a1_birthplace
a1_nationality_present
a1_nationality_birth
a1_race_ethnic
a1_religion
a1_immigration_court (radio: a/b/c)
a1_last_left_country
a1_i94_number
a1_entry_1_date
a1_entry_1_place
a1_entry_1_status
a1_entry_1_expiry
a1_entry_2_date
a1_entry_2_place
a1_entry_2_status
a1_entry_3_date
a1_entry_3_place
a1_entry_3_status
a1_passport_country
a1_passport_number
a1_travel_doc_number
a1_passport_expiry
a1_native_language
a1_fluent_english (radio: yes/no)
a1_other_languages
note_torture_convention (checkbox)
```

### Part A.II Spouse
```
a2_spouse_not_married (checkbox)
a2_spouse_anumber
a2_spouse_passport
a2_spouse_dob
a2_spouse_ssn
a2_spouse_lastname
a2_spouse_firstname
a2_spouse_middlename
a2_spouse_othername
a2_spouse_marriage_date
a2_spouse_marriage_place
a2_spouse_birthplace
a2_spouse_nationality
a2_spouse_race_ethnic
a2_spouse_sex (radio)
a2_spouse_inus (radio: yes/no)
a2_spouse_entry_place
a2_spouse_entry_date
a2_spouse_i94
a2_spouse_visa_status
a2_spouse_current_status
a2_spouse_expiry
a2_spouse_immigration_court (radio)
a2_spouse_previous_arrival
a2_spouse_included (radio)
a2_spouse_location (if not in US)
```

### Part A.II Children (repeated)
```
a2_children_none (checkbox)
a2_children_have (checkbox)
a2_children_total (number)

a2_child1_anumber
a2_child1_passport
a2_child1_marital_status
a2_child1_ssn
a2_child1_lastname
a2_child1_firstname
a2_child1_middlename
a2_child1_dob
a2_child1_birthplace
a2_child1_nationality
a2_child1_race_ethnic
a2_child1_sex
a2_child1_inus (radio)
a2_child1_entry_place
a2_child1_entry_date
a2_child1_i94
a2_child1_visa_status
a2_child1_current_status
a2_child1_expiry
a2_child1_immigration_court
a2_child1_included
a2_child1_location

[Repeat for child2, child3, child4...]
```

*(Truncated for brevity - full listing would include all parts)*

---

## Key Insights for Schema Design

### 1. Hierarchy and Nesting

**Three Levels**:
- **Form**: Top-level container (I-589)
- **Parts**: Major sections (A.I, A.II, A.III, B, C, D, E, F, G)
- **Fields**: Individual inputs

**Sub-Structures**:
- **Groups**: Related fields (address = street + apt + city + state + zip)
- **Tables**: Variable-length repeating records (children, residences)
- **Conditional Sections**: Show/hide based on other fields

### 2. Field Metadata Requirements

Each field needs:
- **id**: Unique identifier (e.g., "a1_lastname")
- **label**: Human-readable label
- **type**: text, textarea, date, radio, checkbox, select, tel, signature
- **validation**: required, format, min/max, pattern
- **conditional**: Show if conditions
- **help_text**: Instructions or examples
- **legal_reference**: Which statute/regulation applies (for legal fields)

### 3. Multi-Entry Patterns

**Three Strategies Observed**:
1. **Fixed Slots with Overflow**: Children (4 slots → Supplement A)
2. **Pre-allocated Rows**: U.S. entries (3 rows provided, expandable)
3. **Open-Ended Tables**: Background sections (2-5 initial rows, infinite expansion)

**Schema Approach**: Define repeating field groups with:
- `min_entries`: Minimum required (often 0 or 1)
- `max_entries`: Maximum allowed (often unlimited)
- `initial_rows`: How many to show initially

### 4. Conditional Logic Syntax

**Observed Patterns**:
- **Simple boolean**: If Q15 = "Yes", show Q16-Q24
- **Checkbox state**: If "not married" checked, hide spouse section
- **Value match**: If total_children > 4, enable Supplement A
- **Mutual exclusion**: Only one of 18a, 18b, 18c can be true

**Schema Needs**:
```json
{
  "show_if": {
    "field": "a2_spouse_inus",
    "operator": "equals",
    "value": "yes"
  }
}
```

### 5. Date Handling Complexity

**Two Date Types**:
- **Full Date**: mm/dd/yyyy (births, entries, marriages)
- **Month/Year**: Mo/Yr (employment, education, residences)

**Schema Implication**: Need `date_precision` field:
- `full`: mm/dd/yyyy
- `month_year`: Mo/Yr
- `year_only`: yyyy (for very old dates)

### 6. Signature Fields Special Handling

**Not Standard Text**:
- May be drawn (canvas)
- May be uploaded image
- May be typed with font
- Requires special capture method

**Schema**: `type: "signature"` with sub-properties:
- `method`: "draw" | "upload" | "type"
- `required`: true
- `signature_box_style`: "bracketed" (for Part D)

### 7. Textarea Size Variability

**Three Sizes Observed**:
- **Small**: 1-2 lines (other names, languages)
- **Medium**: 1/4 page (Part C textareas)
- **Large**: 1/2 page (Part B narratives)

**Schema Property**: `rows` or `size` enum:
- `small`: 2 rows
- `medium`: 5 rows
- `large`: 10 rows

### 8. Help Text and Instructions

**Multiple Instruction Types**:
- **Inline**: "(if any)", "(if applicable)"
- **Below Field**: "include maiden name and aliases"
- **Above Section**: "List your present address first"
- **Separate Instructions**: Reference to separate instruction PDF

**Schema**: `help_text` and `instructions` as separate properties

### 9. Legal Warnings

Some fields have associated warnings:
- Part D: Penalty of perjury
- Part B: Frivolous application consequences
- Part C Q6: Document attachment requirement

**Schema**: `warning_text` property for fields with legal implications

### 10. Form Versioning

**Current Version**: Edition 01/20/25, Expires 09/30/2027

**Schema Must Track**:
- `form_version`: "2025-01-20"
- `expiration_date`: "2027-09-30"
- Field changes between versions
- Backward compatibility

---

## Next Steps for Phase 1A

### Completed
✅ **PDF Structure Analysis**: All 12 pages documented
✅ **Field Inventory**: 200+ fields identified and categorized
✅ **Validation Rules**: Format, conditional, and logical rules documented
✅ **Special Patterns**: Multi-entry, conditional, and signature handling identified

### TODO (Remaining Phase 1A Tasks)

1. **Create Example Schema JSON**:
   - Build JSON representation of Part A.I (25 fields)
   - Validate structure works for all field types
   - Test conditional logic representation

2. **Define FormSchema Model**:
   - Create Python dataclass or Pydantic model
   - Include all metadata properties identified
   - Add validation methods

3. **Document Edge Cases**:
   - Overflow handling (Supplements A and B)
   - Signature capture across contexts
   - Date range validation edge cases
   - Multi-language name handling

4. **Write Schema Specification**:
   - Create `docs/schema_format.md`
   - Document all field types
   - Provide examples for each pattern
   - Define conditional logic syntax

---

**Analysis Status**: ✅ COMPLETE
**Next Phase**: Create FormSchema model and example JSON schemas
