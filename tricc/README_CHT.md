# TRICC CHT output strategy (inherit from XFormCDSS strategy)



## specific nodes

- 'p_name' will be replaced by patient.'name'
- 'select_sex' will be replaced by patient.sex ['f','m']
- 'p_age_day','p_age_month','p_age_year' will be generated from 'date_of_birth'
- 'dob' will be replaced by patient.'date_of_birth'


