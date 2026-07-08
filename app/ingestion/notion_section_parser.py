"""Shared utilities for parsing Notion country guide text into section key-value pairs."""

import re

COUNTRY_ALIASES = {
    "united arab emirates": "UAE",
}

FIELD_TO_SECTION = {
    # --- Basic Labour Laws ---
    "probation period": "probation",
    "notice period during probation": "notice_period_probation",
    "notice period after probation": "termination_notice",
    "notice period": "termination_notice",
    "working hours": "working_hours",
    "overtime hours": "overtime",
    "overtime": "overtime",
    "end of service benefit": "end_of_service_benefit",
    "end of service benefits": "end_of_service_benefit",
    "annual bonus": "annual_bonus",
    # --- Leave Policy ---
    "annual earned leaves": "annual_leave",
    "annual vacation earned leaves": "annual_leave",
    "annual leave": "annual_leave",
    "sick leave": "sick_leave",
    "casual leave": "casual_leave",
    "public holidays": "public_holidays",
    "maternity leave": "maternity_leave",
    "paternity leave": "paternity_leave",
    "childcare leaves": "childcare_leave",
    "compassionate leave": "compassionate_leave",
    "wedding leaves": "wedding_leave",
    "leave carry forward policy": "leave_carry_forward",
    "pilgrimage leaves": "pilgrimage_leave",
    "hajj leaves": "hajj_leave",
    "shared parental leaves": "shared_parental_leave",
    "parental bereavement leave": "parental_bereavement_leave",
    "jury service": "jury_service",
    "magistrate duty": "magistrate_duty",
    "extended leave career break": "extended_leave",
    "duvet days": "duvet_days",
    "garden leave": "garden_leave",
    "hospitalisation leave": "hospitalisation_leave",
    "military leave": "military_leave",
    "business leave": "business_leave",
    "adoption leaves": "adoption_leave",
    "adoption leave": "adoption_leave",
    "suffrage leave": "suffrage_leave",
    "family day leave": "family_day_leave",
    "personal leave": "personal_leave",
    "additional leave": "additional_leave",
    "holiday bonus": "holiday_bonus",
    "vacation premium": "vacation_premium",
    "holiday pay": "holiday_pay",
    "training hours": "training_hours",
    "parental leaves": "parental_leave",
    "parental leave": "parental_leave",
    "other leaves": "other_leaves",
    "any other leaves": "other_leaves",
    "additional leaves": "other_leaves",
    "statutory leaves": "other_leaves",
    "bereavement leave": "bereavement_leave",
    "festival bonus": "festival_bonus",
    "13th and or 14th month pay": "thirteenth_month_pay",
    "13th month pay": "thirteenth_month_pay",
    "13th month": "thirteenth_month_pay",
    "holiday pay allowance": "holiday_pay_allowance",
    "holiday vacation bonus": "holiday_pay_allowance",
    "holiday pay accrual": "holiday_pay_allowance",
    "overtime pay": "overtime_pay",
    "overtime hours pay": "overtime_pay",
    "overtime hours pay rule": "overtime_pay",
    "overtime pay rates": "overtime_pay",
    "overtime rate": "overtime_pay",
    "end of service clause": "end_of_service_benefit",
    "end of service benefit gratuity": "end_of_service_benefit",
    "end of service clause gratuity": "end_of_service_benefit",
    "gratuity": "end_of_service_benefit",
    "study leave": "study_leave",
    "education leave": "education_leave",
    "special leave": "special_leave",
    "care leave": "care_leave",
    "care leaves": "care_leave",
    "care giver leaves": "care_leave",
    "care leave family responsibility leave": "care_leave",
    "family caregiver leave": "care_leave",
    "family-care leave": "care_leave",
    "remote work allowance": "remote_work_allowance",
    "reimbursement for remote work": "remote_work_allowance",
    "working from home": "remote_work_allowance",
    "long service leave": "long_service_leave",
    "long service pay": "long_service_pay",
    "seniority bonus": "seniority_bonus",
    "profit sharing": "profit_sharing",
    "funeral leave": "funeral_leave",
    "leave for pre-natal examination": "prenatal_leave",
    "parental care leave": "parental_care_leave",
    "pregnancy status leave": "pregnancy_leave",
    "breastfeeding leave": "breastfeeding_leave",
    "breastfeeding break": "breastfeeding_leave",
    "lactation leave": "breastfeeding_leave",
    "domestic violence leave": "domestic_violence_leave",
    "solo parent leave": "solo_parent_leave",
    "menstrual leave": "menstrual_leave",
    "fertility leave": "fertility_leave",
    "shared parental leave": "shared_parental_leave",
    "job-seeking leave": "job_seeking_leave",
    "contract durations": "contract_durations",
    "length of service based increment": "service_increment",
    "vacation accruals": "vacation_accruals",
    "industrial injuries insurance": "industrial_injuries_insurance",
    "activity report": "activity_report",
    "annual meeting": "annual_meeting",
    "pre- adoptive leave": "adoption_leave",
    "pilgrimage hajj leaves": "pilgrimage_leave",
    "work related injuries": "work_related_injuries",
    "house moving leave": "house_moving_leave",
    "jury duty": "jury_service",
    "union leave": "union_leave",
    "military recruitment": "military_leave",
    "disabled child": "disabled_child_leave",
    "serious illness of a close family member": "family_illness_leave",
    "accident illness or death of a family member": "family_illness_leave",
    # --- Payroll & Taxation ---
    "payout currency": "payout_currency",
    "pay out currency": "payout_currency",
    "minimum wages": "minimum_wage",
    "minimum wage": "minimum_wage",
    "income tax": "income_tax",
    "employer cost": "employer_cost",
    "additional employer costs": "additional_employer_costs",
    "vat": "vat",
    "severance accrual": "severance_accrual",
    "severance accruals": "severance_accrual",
    "emiratisation fee": "emiratisation_fee",
    "payroll tax": "payroll_tax",
    # --- Benefits ---
    "public health insurance": "public_health_insurance",
    "private health insurance": "private_health_insurance",
    "health insurance": "health_insurance",
    "social security": "social_security",
    "mandatory pension plan": "mandatory_pension",
    "severance fund": "severance_fund",
    "life insurance": "life_insurance",
    "pension": "pension",
    "employee benefits": "employee_benefits",
    # --- Other Services ---
    "devices": "devices",
    "co-working spaces": "coworking_spaces",
    "expats": "expatriate_employment",
    "expatriate employment": "expatriate_employment",
    # --- Important Dates ---
    "pay date": "pay_date",
    "expenses adjustment cut off": "expenses_cutoff",
    "onboarding cut off": "onboarding_cutoff",
    # --- Termination ---
    "termination scenarios": "termination_scenarios",
    "severance payable": "severance_payable",
    "redundancy allowance": "redundancy_allowance",
    # --- Onboarding ---
    "onboarding time": "onboarding_time",
    "enrolment in private health insurance": "onboarding_health_insurance",
    "enrollment in private health insurance": "onboarding_health_insurance",
    "enrollment in private health ins.": "onboarding_health_insurance",
    "device shipment": "device_shipment",
    "additional onboarding requirement": "additional_onboarding_requirement",
    "amount payable upon termination or resignation": "termination_payout",
    "full and final settlement pay date for offboardings": "final_settlement_date",
    "health and safety": "health_and_safety",
    "medical examination": "medical_examination",
    # --- Other ---
    "employer obligations": "employer_obligations",
    "withholding tax": "withholding_tax",
    "tax filing": "tax_filing",
    "industrial relations": "industrial_relations",
    "workplace safety": "workplace_safety",
    "osh obligations": "osh_obligations",
    "work permit": "work_permit",
    "work visa": "work_visa",
}

_LEFT_LABEL_SECTIONS = {
    "benefits", "other services", "important dates",
    "termination", "onboarding", "employer obligations",
}


def canonical_country(name: str) -> str:
    return COUNTRY_ALIASES.get(name.lower(), name.strip())


def _normalise_label(text: str) -> str:
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[/,&]", " ", text)
    return re.sub(r"\s+", " ", text.lower()).strip()


def _match_field(text: str):
    norm = _normalise_label(text)
    if norm in FIELD_TO_SECTION:
        return FIELD_TO_SECTION[norm]
    return None


def parse_sections(text: str) -> dict:
    """
    Parse Notion page text (produced by NotionIngestionService._blocks_to_text)
    into {section_key: value} pairs.

    Right-label sections (Basic Labour Laws, Leave Policy, Payroll & Taxation):
      Multi-line values end with ``last-line | FieldLabel``.  Plain lines before
      a labelled line are the *beginning* of that value -> accumulate forward in
      ``pending`` and flush into the next matched field.

    Left-label sections (Benefits, Other Services, Termination, Onboarding, Important Dates):
      Each row starts with ``FieldLabel | value``.  Plain lines *after* a matched
      row are continuations of that row's value -> append to ``last_key``.
    """
    sections: dict = {}
    current_heading = ""
    last_key = None
    pending: list = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(r"^#{2,4}\s+(.+)", line)
        if heading_match:
            current_heading = heading_match.group(1).strip().lower()
            last_key = None
            pending = []
            continue

        if current_heading in ("was this information helpful?",):
            continue

        is_left_label = any(s in current_heading for s in _LEFT_LABEL_SECTIONS)

        if " | " in line or line.startswith("| "):
            if line.startswith("| "):
                left, right = "", line[2:].strip()
            else:
                left, right = line.split(" | ", 1)
                left, right = left.strip(), right.strip()

            if is_left_label:
                section_key = _match_field(left)
                value = right if section_key else None
                if not section_key:
                    section_key = _match_field(right)
                    value = left if section_key else None
            else:
                section_key = _match_field(right)
                value = left if section_key else None
                if not section_key:
                    section_key = _match_field(left)
                    value = right if section_key else None

            if section_key and (value or pending):
                if pending:
                    parts = pending + ([value] if value else [])
                    value = "\n".join(parts)
                    pending = []
                if section_key in sections:
                    sections[section_key] += "\n" + value
                else:
                    sections[section_key] = value
                last_key = section_key
            elif is_left_label and last_key:
                sections[last_key] += "\n" + line
            else:
                if is_left_label:
                    last_key = None
                else:
                    pending.append(line)
        else:
            if is_left_label:
                if last_key:
                    sections[last_key] += "\n" + line
            else:
                pending.append(line)

    return sections
