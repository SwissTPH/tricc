
import json
from fhir.resources.codesystem import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty
)
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.range import Range
from fhir.resources.quantity import Quantity
from fhir.resources.coding import Coding

class CodeSystemBuilder:
    def __init__(self, code, name, data):
        self.data = data
        full_order = json.loads(self.data['full_order_json'])
        concepts = self._process_full_order(full_order)
        self.code_system = CodeSystem(
            id=code,
            url=f"http://example.com/fhir/CodeSystem/{code}",
            version="1.0.0",
            name=name,
            title=name,
            status="draft",
            description=f"Code system for {name}",
            content="complete",
            concept=concepts
        )
        
    def _process_full_order(self, full_order, parent=None):
        concepts = []
        gbc_main_order = []
        
        for item in full_order:
            node_id = item.get('id', None)
            node = (
                self.data['medal_r_json']['nodes'].get(str(node_id), None)
                if node_id else None
            )
            if not node:
                node = {'id': item.get('id', item['title'].lower().replace(' ', '_')),
                        'label': {'en': item['title']}}
            label = node.get('label', {'en': 'Unknown'})
            display = list(label.values())[0]
            concept = CodeSystemConcept(
                code=node['id'],
                display=display
            )
            if len(label) > 0 and display != 'Unknown':
                concept.designation = []
                for k, v in label.items():
                    concept.designation.append(CodeSystemConceptDesignation(
                        language=k,
                        use=Coding(
                            system="http://terminology.hl7.org/CodeSystem/designation-usage",
                            code="display"
                        ),
                        value=v
                    ))
            concept.property = []
            context = item.get('parent', parent)
            if context:
                concept.property.append(CodeSystemConceptProperty(
                    code="context",
                    valueCode=context
                ))

            if 'value_format' in node:
                concept.property.append(CodeSystemConceptProperty(
                    code="type", 
                    valueCode=node['value_format']
                ))

            if 'display_format' in node:
                concept.property.append(CodeSystemConceptProperty(
                    code="format", 
                    valueCode=node['display_format']
                ))

            if 'cut_off_start' in node or 'cut_off_end' in node:
                start = node.get('cut_off_start', None)
                start_qty = Quantity(
                    value=start,
                    unit="months",
                    system="http://unitsofmeasure.org",
                    code="mo"
                )if start else None
                end = node.get('cut_off_end',None)
                end_qty = Quantity(
                    value=end,
                    unit="months",
                    system="http://unitsofmeasure.org",
                    code="mo"
                ) if end else None
                    
                if start or end:
                    concept.property.append(CodeSystemConceptProperty(
                        code="age",
                        valueRange=Range(
                            low=start_qty,
                            high=end_qty
                        )
                    ))     
            
            # Process child concepts
            if 'children' in item and item['children']:
                concepts += self._process_full_order(item['children'], parent=node['id'])
                normalized_child_id = [str(i.get('id', i.get('subtitle_name', 'ERROR'))) for i in item['children']]
                concept.property.append(CodeSystemConceptProperty(
                    code="order",
                    valueString=','.join(normalized_child_id)
                ))
                if not parent:
                    gbc_main_order.append(node['id'])
            concepts.append(concept)
        # adding overall order
        if gbc_main_order:
            concepts.append(CodeSystemConcept(
                    code='__root__',
                    display="Overall order",
                    property=[CodeSystemConceptProperty(
                        code="order",
                        valueString=','.join(gbc_main_order)
                    )]
            ))
        
        return concepts
    

