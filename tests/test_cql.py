import unittest

from tricc_oo.converters.cql_to_operation import cqlToXlsFormVisitor, transform_cql_to_operation
from tricc_oo.models.base import  TriccOperator, TriccOperation, TriccStatic, TriccReference

class TestCql(unittest.TestCase):
    def test_and(self):
        if_cql = "\"p_weight\" is not null and \"p_age\" > 2"
        dg_operation = transform_cql_to_operation(if_cql)
        dg_expected = TriccOperation(
            operator=TriccOperator.AND,
            reference=[
                TriccOperation(
                    operator=TriccOperator.NOT,
                    reference=[
                        TriccOperation(
                            operator=TriccOperator.ISNULL,
                            reference=[TriccReference("p_weight")]
                        )
                    ]
                ),
                TriccOperation(
                    operator=TriccOperator.MORE,
                    reference=[
                        TriccReference("p_age"),
                        TriccStatic(
                            value=2
                        )
                    ]
                )
            ]
        )
        self.assertEqual(str(dg_operation), str(dg_expected))
    
   
    def test_durg_doage(self):
        if_cql = "DrugDosage('paracetamol', \"p_weight\", \"p_age\")"
        dg_operation = transform_cql_to_operation(if_cql)
        dg_expected = TriccOperation(
            operator=TriccOperator.DRUG_DOSAGE,
            reference=[
                TriccStatic(value='paracetamol'),
                TriccReference("p_weight"),
                TriccReference("p_age")
            ]
        )
        self.assertEqual(str(dg_operation), str(dg_expected))
    
    def test_if(self):
        if_cql = "if AgeInDays() < 60 then 'newborn' else 'child'"
        if_operation = transform_cql_to_operation(if_cql)
        if_expected = TriccOperation(
            operator=TriccOperator.IF,
            reference=[
                TriccOperation(
                    operator=TriccOperator.LESS,
                    reference=[
                        TriccOperation(
                            operator=TriccOperator.AGE_DAY,
                            reference=[]
                        ),
                        TriccStatic(
                            value=60
                        )
                    ]
                ),
                TriccStatic(value='newborn'),
                TriccStatic(value='child'),
            ]
        )
        self.assertEqual(str(if_operation), str(if_expected))

    def test_case(self):
        case_cql = """
        case AgeInMonths() 
        when 0 then 'newborn' 
        when 1 then 'newborn' 
        else 'child' end
        """
        case_operation = transform_cql_to_operation(case_cql)
        case_expected = TriccOperation(
            operator=TriccOperator.CASE,
            reference=[
                TriccOperation(
                    operator=TriccOperator.AGE_MONTH,
                    reference=[]
                ),
                [
                    TriccStatic(
                        value=0
                    ),
                    TriccStatic(
                        value="newborn"
                    )
                ],
                [
                    TriccStatic(
                        value=1
                    ),
                    TriccStatic(
                        value="newborn"
                    )
                ],
                TriccStatic(value='child'),
            ]
        )
        self.assertEqual(str(case_operation), str(case_expected))

    def test_ifs(self):
        case_cql = """
        case 
        when AgeInMonths() <= 2 then 'newborn' 
        when AgeInYears() > 5 then 'teen' 
        else 'child' end
        """
        case_operation = transform_cql_to_operation(case_cql)
        case_expected = TriccOperation(
            operator=TriccOperator.CASE,
            reference=[
                [
                    TriccOperation(
                        operator=TriccOperator.LESS_OR_EQUAL,
                        reference=[
                            TriccOperation(
                                operator=TriccOperator.AGE_MONTH,
                                reference=[]
                            ),
                            TriccStatic(
                                value=2
                            )
                        ]
                    ),
                    TriccStatic(
                        value="newborn"
                    )
                ],
                [
                    TriccOperation(
                        operator=TriccOperator.MORE,
                        reference=[
                            TriccOperation(
                                operator=TriccOperator.AGE_YEAR,
                                reference=[]
                            ),
                            TriccStatic(
                                value=5
                            )
                        ]
                    ),
                    TriccStatic(
                        value="teen"
                    )
                ],
                TriccStatic(value='child'),
            ]
        )
        self.assertEqual(str(case_operation), str(case_expected))


    def test_minus(self):
        minus_cql ="""
        "CHE.B23.DE68" is false and 
"CHE.B23.DE69" is false and 
"CHE.B23.DE70" is false and 
"age_in_months" < 60 and
case 
when  "age_in_months" >= 6  then ( "WFL" >= -3 and "WFL" < -2)
when ("CHE.B6.DE19" >= 115 and "CHE.B6.DE19" < 125) then true
when "age_in_months" >= 24  then ("WFH" >= -3 and "WFH" < -2)
else  ("WFL" >= -3 and "WFL" < -2) 
end
        """
        # minus_cql = """
        # ("age_in_months" < 6 and "WFL" >= -3 and "WFL" < -2) is true
        # """
        minus_operation = transform_cql_to_operation(minus_cql)
        minus_expected = None
        self.assertEqual(str(minus_operation), str(minus_expected))
        
if __name__ == '__main__':
    unittest.main()