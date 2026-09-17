library "cohort-fup-registration" version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers
include "cohort-fup-Helper" version '1.0.0' called Helper

context Patient



define Calc_load_t_date_clin_ev: Helper.GetEncounterObservationValue('t_date_clin_ev', null, null)

define Calc_load_t_aht_tx_cat: Helper.GetEncounterObservationValue('t_aht_tx_cat', null, null)

define Calc_load_t_date_cervical_cancer: Helper.GetEncounterObservationValue('t_date_cervical_cancer', null, null)

define Calc_load_t_cvd_risk: Helper.GetEncounterObservationValue('t_cvd_risk', null, null)

define Calc_load_t_hysterectomy: Helper.GetEncounterObservationValue('t_hysterectomy', null, null)

define Calc_load_t_date_warn_symp: Helper.GetEncounterObservationValue('t_date_warn_symp', null, null)

define Calc_load_t_date_blindness: Helper.GetEncounterObservationValue('t_date_blindness', null, null)

define Calc_load_t_date_heart_failure: Helper.GetEncounterObservationValue('t_date_heart_failure', null, null)

define Calc_load_t_stroke_stat: Helper.GetEncounterObservationValue('t_stroke_stat', null, null)

define Calc_load_t_date_last_vis: Helper.GetEncounterObservationValue('t_date_last_vis', null, null)

define Calc_load_t_sce_type: Helper.GetEncounterObservationValue('t_sce_type', null, null)

define Calc_load_t_dm_txs: Helper.GetEncounterObservationValue('t_dm_txs', null, null)

define Calc_load_t_date_mi: Helper.GetEncounterObservationValue('t_date_mi', null, null)

define Calc_load_age: Helper.GetEncounterObservationValue('age', null, null)

define Calc_load_t_weight: Helper.GetEncounterObservationValue('t_weight', null, null)

define Calc_load_t_aht_dxs: Helper.GetEncounterObservationValue('t_aht_dxs', null, null)

define Calc_load_t_hiv_stat: Helper.GetEncounterObservationValue('t_hiv_stat', null, null)

define Calc_load_t_breastfeeding: Helper.GetEncounterObservationValue('t_breastfeeding', null, null)

define Calc_load_t_date_clin_ev_rep: Helper.GetEncounterObservationValue('t_date_clin_ev_rep', null, null)

define Calc_load_t_pregnant: Helper.GetEncounterObservationValue('t_pregnant', null, null)

define Calc_load_t_bp_status: Helper.GetEncounterObservationValue('t_bp_status', null, null)

define Calc_load_t_date_cohort_bsl: Helper.GetEncounterObservationValue('t_date_cohort_bsl', null, null)

define Calc_load_dob3: Helper.GetEncounterObservationValue('dob3', null, null)

define Calc_load_t_cesi_type: Helper.GetEncounterObservationValue('t_cesi_type', null, null)

define Calc_load_t_tb_history: Helper.GetEncounterObservationValue('t_tb_history', null, null)

define Calc_load_t_other_drugs: Helper.GetEncounterObservationValue('t_other_drugs', null, null)

define Calc_load_t_thrombosis: Helper.GetEncounterObservationValue('t_thrombosis', null, null)

define Calc_load_t_drug_reaction: Helper.GetEncounterObservationValue('t_drug_reaction', null, null)

define Calc_load_t_peripheral_arterial_disease: Helper.GetEncounterObservationValue('t_peripheral_arterial_disease', null, null)

define Calc_load_t_smok_stat: Helper.GetEncounterObservationValue('t_smok_stat', null, null)

define Calc_load_t_rbg: Helper.GetEncounterObservationValue('t_rbg', null, null)

define Calc_load_t_ckd: Helper.GetEncounterObservationValue('t_ckd', null, null)

define Calc_load_t_hiv_care_status: Helper.GetEncounterObservationValue('t_hiv_care_status', null, null)

define Calc_load_t_other_dx: Helper.GetEncounterObservationValue('t_other_dx', null, null)

define Calc_load_t_bg_cat: Helper.GetEncounterObservationValue('t_bg_cat', null, null)

define Calc_load_t_dm_tx: Helper.GetEncounterObservationValue('t_dm_tx', null, null)

define Calc_load_t_clin_ev_details: Helper.GetEncounterObservationValue('t_clin_ev_details', null, null)

define Calc_load_t_mi_stat: Helper.GetEncounterObservationValue('t_mi_stat', null, null)

define Calc_load_dob1: Helper.GetEncounterObservationValue('dob1', null, null)

define Calc_load_t_date_weight: Helper.GetEncounterObservationValue('t_date_weight', null, null)

define Calc_load_t_aht_tx: Helper.GetEncounterObservationValue('t_aht_tx', null, null)

define Calc_load_dob2: Helper.GetEncounterObservationValue('dob2', null, null)

define Calc_load_t_date_stroke: Helper.GetEncounterObservationValue('t_date_stroke', null, null)

define Calc_load_t_chronic_liver_disease: Helper.GetEncounterObservationValue('t_chronic_liver_disease', null, null)

define Calc_load_t_sterilized: Helper.GetEncounterObservationValue('t_sterilized', null, null)

define Calc_load_t_aht_drugs: Helper.GetEncounterObservationValue('t_aht_drugs', null, null)

define Calc_load_t_date_menarche_gr: Helper.GetEncounterObservationValue('t_date_menarche_gr', null, null)

define Calc_load_t_date_height: Helper.GetEncounterObservationValue('t_date_height', null, null)

define Calc_load_t_atorva_stat: Helper.GetEncounterObservationValue('t_atorva_stat', null, null)

define Calc_load_t_date_art_stat: Helper.GetEncounterObservationValue('t_date_art_stat', null, null)

define Calc_load_t_bg_status: Helper.GetEncounterObservationValue('t_bg_status', null, null)

define Calc_load_t_aht_txs: Helper.GetEncounterObservationValue('t_aht_txs', null, null)

define Calc_load_t_other_tx: Helper.GetEncounterObservationValue('t_other_tx', null, null)

define Calc_load_t_height: Helper.GetEncounterObservationValue('t_height', null, null)

define Calc_load_t_date_hiv_stat: Helper.GetEncounterObservationValue('t_date_hiv_stat', null, null)

define Calc_load_t_bmi: Helper.GetEncounterObservationValue('t_bmi', null, null)

define Calc_load_t_aht_diag_cat: Helper.GetEncounterObservationValue('t_aht_diag_cat', null, null)

define Calc_load_t_date_smok_stat: Helper.GetEncounterObservationValue('t_date_smok_stat', null, null)

define Calc_load_t_art: Helper.GetEncounterObservationValue('t_art', null, null)

define Calc_load_t_clin_ev_type: Helper.GetEncounterObservationValue('t_clin_ev_type', null, null)

define Calc_load_t_blindness: Helper.GetEncounterObservationValue('t_blindness', null, null)

define Calc_load_t_ass_stat: Helper.GetEncounterObservationValue('t_ass_stat', null, null)

define Calc_load_t_date_initial_symp: Helper.GetEncounterObservationValue('t_date_initial_symp', null, null)

define Calc_load_t_cervical_cancer: Helper.GetEncounterObservationValue('t_cervical_cancer', null, null)

define Calc_load_t_dm_drugs: Helper.GetEncounterObservationValue('t_dm_drugs', null, null)

define Calc_load_t_menarche: Helper.GetEncounterObservationValue('t_menarche', null, null)

define Calc_load_t_date_preg_bf: Helper.GetEncounterObservationValue('t_date_preg_bf', null, null)

define Calc_load_t_date_cesi_gr: Helper.GetEncounterObservationValue('t_date_cesi_gr', null, null)

define Calc_load_t_heart_failure: Helper.GetEncounterObservationValue('t_heart_failure', null, null)

define Calc_load_t_date_drug_reaction: Helper.GetEncounterObservationValue('t_date_drug_reaction', null, null)

define Calc_load_t_date_thrombosis: Helper.GetEncounterObservationValue('t_date_thrombosis', null, null)

define Calc_load_t_aht_fc_rsn: Helper.GetEncounterObservationValue('t_aht_fc_rsn', null, null)

define Calc_load_t_metfin_dose: Helper.GetEncounterObservationValue('t_metfin_dose', null, null)

define Calc_load_t_ref_arm: Helper.GetEncounterObservationValue('t_ref_arm', null, null)

define Calc_load_t_date_chronic_liver_disease: Helper.GetEncounterObservationValue('t_date_chronic_liver_disease', null, null)

define Calc_load_t_date_ckd: Helper.GetEncounterObservationValue('t_date_ckd', null, null)

define Calc_load_t_dm_dxs: Helper.GetEncounterObservationValue('t_dm_dxs', null, null)

define Calc_load_t_date_neuropathy: Helper.GetEncounterObservationValue('t_date_neuropathy', null, null)

define Calc_load_t_warn_symp: Helper.GetEncounterObservationValue('t_warn_symp', null, null)

define Calc_load_t_lung_disease: Helper.GetEncounterObservationValue('t_lung_disease', null, null)

define Calc_load_t_date_peripheral_arterial_disease: Helper.GetEncounterObservationValue('t_date_peripheral_arterial_disease', null, null)

define Calc_load_t_fbg: Helper.GetEncounterObservationValue('t_fbg', null, null)

define Calc_load_t_date_lung_disease: Helper.GetEncounterObservationValue('t_date_lung_disease', null, null)

define Calc_load_t_diabetic_foot: Helper.GetEncounterObservationValue('t_diabetic_foot', null, null)

define Calc_load_t_neuropathy: Helper.GetEncounterObservationValue('t_neuropathy', null, null)

define Calc_load_t_date_diabetic_foot: Helper.GetEncounterObservationValue('t_date_diabetic_foot', null, null)

define Calc_load_t_clin_ev: Helper.GetEncounterObservationValue('t_clin_ev', null, null)

define Calc_load_t_dm_fc_rsn: Helper.GetEncounterObservationValue('t_dm_fc_rsn', null, null)

define Calc_load_t_dia_avg: Helper.GetEncounterObservationValue('t_dia_avg', null, null)

define Calc_load_t_amlohct_dose: Helper.GetEncounterObservationValue('t_amlohct_dose', null, null)

define Calc_load_t_date_sce_gr: Helper.GetEncounterObservationValue('t_date_sce_gr', null, null)

define Calc_load_t_sys_avg: Helper.GetEncounterObservationValue('t_sys_avg', null, null)

define Calc_load_sex: Helper.GetEncounterObservationValue('sex', null, null)

define Calc_pnav_rel_1: true

define Calc_pnav_goto_2: true

define Calc_pnav_rel_3: true

define Calc_pnav_rel_4: true

define Calc_pnav_rel_5: true

define Calc_pnav_rel_6: true

define Calc_pnav_rel_7: true

define Calc_pnav_rel_8: true

define Calc_pnav_rel_9: true

define Calc_pnav_rel_10: true

define Calc_pnav_rel_11: true

define Calc_phhxIR5POLgwOchVgMte4_18: true

define Calc_pVNaK7BrzqFYHAwkys907_91: true

define Calc_date_height: Today()

define Calc_date_weight: Today()

define Calc_p_tJBUlJj8Pxc16BJfXB2_3: true

define Calc_date_menarche_gr: Today()

define Calc_date_smok_stat: Today()

define Calc_p7snVGWoBI1X0_9_Hhpmj_96: true

define Calc_date_art_stat: Today()

define Calc_date_hiv_stat: Today()

define Calc_date_initial_symp: Today()

define Calc_date_last_vis: Today()

define Calc_date_preg_bf: Today()

define Calc_date_cohort_bsl: Today()

define Dedup_educ: Helper.GetObservationValue('educ')

define Dedup_employ: Helper.GetObservationValue('employ')

define Dedup_marstat: Helper.GetObservationValue('marstat')

define Dedup_hiv_stat_cur: Helper.GetObservationValue('hiv_stat_cur')

define Dedup_art: Helper.GetObservationValue('art')

define Dedup_tb_history: Helper.GetObservationValue('tb_history')

define Dedup_any_comor: Helper.GetObservationValue('any_comor')

define Dedup_mi: Helper.GetObservationValue('mi')

define Dedup_stroke: Helper.GetObservationValue('stroke')

define Dedup_ckd: Helper.GetObservationValue('ckd')

define Dedup_thrombosis: Helper.GetObservationValue('thrombosis')

define Dedup_chronic_liver_disease: Helper.GetObservationValue('chronic_liver_disease')

define Dedup_heart_failure: Helper.GetObservationValue('heart_failure')

define Dedup_lung_disease: Helper.GetObservationValue('lung_disease')

define Dedup_cervical_cancer: Helper.GetObservationValue('cervical_cancer')

define Dedup_blindness: Helper.GetObservationValue('blindness')

define Dedup_peripheral_arterial_disease: Helper.GetObservationValue('peripheral_arterial_disease')

define Dedup_neuropathy: Helper.GetObservationValue('neuropathy')

define Dedup_diabetic_foot: Helper.GetObservationValue('diabetic_foot')

define Dedup_date_diabetic_foot: Helper.GetObservationValue('date_diabetic_foot')

define Dedup_date_neuropathy: Helper.GetObservationValue('date_neuropathy')

define Dedup_date_peripheral_arterial_disease: Helper.GetObservationValue('date_peripheral_arterial_disease')

define Dedup_date_blindness: Helper.GetObservationValue('date_blindness')

define Dedup_date_cervical_cancer: Helper.GetObservationValue('date_cervical_cancer')

define Dedup_cervical_cancer_tx: Helper.GetObservationValue('cervical_cancer_tx')

define Dedup_date_lung_disease: Helper.GetObservationValue('date_lung_disease')

define Dedup_date_heart_failure: Helper.GetObservationValue('date_heart_failure')

define Dedup_date_chronic_liver_disease: Helper.GetObservationValue('date_chronic_liver_disease')

define Dedup_date_thrombosis: Helper.GetObservationValue('date_thrombosis')

define Dedup_date_ckd: Helper.GetObservationValue('date_ckd')

define Dedup_date_stroke: Helper.GetObservationValue('date_stroke')

define Dedup_date_mi: Helper.GetObservationValue('date_mi')

define Dedup_smok_stat: Helper.GetObservationValue('smok_stat')

define Dedup_menarche_yn: Helper.GetObservationValue('menarche_yn')

define Dedup_vasectomy: Helper.GetObservationValue('vasectomy')

define Dedup_hysterectomy_yn: Helper.GetObservationValue('hysterectomy_yn')

define Dedup_tubal_ligation: Helper.GetObservationValue('tubal_ligation')

define Dedup_weight: Helper.GetObservationValue('weight')

define Dedup_height: Helper.GetObservationValue('height')

define Dedup_symp_yn: Helper.GetObservationValue('symp_yn')

define Dedup_sev_symp_yn: Helper.GetObservationValue('sev_symp_yn')

define Dedup_non_sev_symp: Helper.GetObservationValue('non_sev_symp')

define Dedup_symptom: Helper.GetObservationValue('symptom')

define Dedup_sup_call_warn_yn: Helper.GetObservationValue('sup_call_warn_yn')

define Dedup_initial_symp_details: Helper.GetObservationValue('initial_symp_details')

define Dedup_symp_ref: Helper.GetObservationValue('symp_ref')

define Dedup_symp_ref_refuse: Helper.GetObservationValue('symp_ref_refuse')

define Dedup_symp_ref_refuse_spec: Helper.GetObservationValue('symp_ref_refuse_spec')

define Dedup_no_sup_call_warn_rs: Helper.GetObservationValue('no_sup_call_warn_rs')

define Dedup_other_symp: Helper.GetObservationValue('other_symp')

define Dedup_oth_symp_ref: Helper.GetObservationValue('oth_symp_ref')

define Dedup_cur_pregnant: Helper.GetObservationValue('cur_pregnant')

define Dedup_last_breastfeeding_stat: Helper.GetObservationValue('last_breastfeeding_stat')

define Dedup_cur_breastfeeding: Helper.GetObservationValue('cur_breastfeeding')

define Dedup_last_preg_stat: Helper.GetObservationValue('last_preg_stat')
