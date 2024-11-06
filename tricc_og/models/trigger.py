from strenum import StrEnum
from enum import auto


class TriccTriggers(StrEnum):   
    registration = "registration"  # patient update
    patient_admission_recommendation = "patient-admission-recommendation"  # not in CPG
    triage = "triage"
    guideline_based_care = "guideline-based-care" # not in CPG
    history_and_physical = "history-and-physical"  # data collection  
    determine_diagnosis = "determine-diagnosis"  # propose diagnostic
    dispense_medications = "dispense-medications"  # treatment proposal
    provide_counseling = "provide-counseling"  # specific recommendation
    monitor_and_follow_up_of_patient = "monitor-and-follow-up-of-patient"  # ???
    discharge_referral_of_patient = "discharge-referral-of-patient"  # generic recommendation / referaö
    appointment_planning = "appointment-planning"  # not in cpg


    def __iter__(self):
        return iter(self.__members__.values())

    def __next__(self):
        return next(iter(self))