library Functions version '1.0'

/*
@description: Adult from a declared answer, else from the age (years)
@retrieve: false
@param.age: fallback=age_years retrievals=#age_years
*/
define function IsAdult(age Integer, declared Boolean) returns Boolean:
  Coalesce(declared, age >= 18)
