
import json
from types import SimpleNamespace

from tricc.converters.mc_to_tricc import create_activity,build_relevance,fetch_reference,fetch_condition
from tricc.models.tricc import *
from tricc.strategies.base_input_strategy import BaseInputStrategy

media_path = "./"
class MedalCStrategy(BaseInputStrategy):
  def build_tricc_graph(self, in_filepath, media_path):
      f = open(in_filepath)
      js_full = json.load(f)
      pages = {}
      start_page=None
      js_fullorder =  js_full['medal_r_json']['config']['full_order']
      js_nodes = js_full['medal_r_json']['nodes']
      js_final_diagnoses = js_full['medal_r_json']['final_diagnoses']
      js_diagnoses = js_full['medal_r_json']['diagnoses']
      js_diagrams = js_full['medal_r_json']['diagram']
      
      js_all = {**js_nodes, **js_diagnoses,**js_final_diagnoses }
      js_nodes['first_name'] = {
          "id":'first_name' ,
          "label": {
            "en": "First Name",
            "fr": "Prénom"
          },
          "type": "Question",
          "category": "patient_data",
          "value_format": "String"
      }
      js_nodes['last_name'] = {
          "id":'last_name' ,
          "label": {
            "en": "Last Name",
            "fr": "Nom de famille"
          },
          "type": "Question",
          "category": "patient_data",
          "value_format": "String"
      }
      

      js_nodes['birth_date'] = {
          "id":'birth_date' ,
          "label": {
            "en": "Date of birth",
            "fr": "Date de naissance"
          },
          "type": "Question",
          "category": "patient_data",
          "value_format": "Date"
      }

      
      is_first=True
      last_page = None
      for key, stage in js_fullorder.items():
          page = create_activity(stage, key, media_path, js_nodes, last_page)
          last_page = page  
          pages[key]=page
          if is_first :
              start_page = page
              page.root.form_id=js_full['id']
              page.root.label=js_full['name']
          is_first = False 
      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]
      # add p_age
      brith_date_node = list(filter(lambda gp: gp.id == 'birth_date', all_nodes))[0]
      age_node = TriccNodeCalculate(
        name = 'p_age_day',
        reference = [brith_date_node],
        expression_reference = 'int((today()-date(${{{}}})))',
        id = 'p_age_day',
        activity = brith_date_node.activity,
        group = brith_date_node.activity
      )
      set_prev_next_node(brith_date_node,age_node)
      brith_date_node.activity.nodes.append(age_node)
      yi_node = TriccNodeRhombus(
        name = 'yi',
        reference = [age_node],
        expression_reference = '${{{}}}< 62',
        id = 'yi',
        activity = brith_date_node.activity,
        group = brith_date_node.activity
      )
      set_prev_next_node(age_node,yi_node)
      brith_date_node.activity.nodes.append(yi_node)
      
      child_node = TriccNodeExclusive(
        id = generate_id(),
        activity = brith_date_node.activity,
        group = brith_date_node.activity
      )
      set_prev_next_node(yi_node,child_node)
      brith_date_node.activity.nodes.append(child_node)
      
      # add the missing nodes
      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]
      node_id_covered = [node.id for node in all_nodes ]
      mode_id_missing= list(filter(lambda key: key not in node_id_covered ,js_nodes))
      page = create_activity(mode_id_missing, "other_nodes", media_path, js_nodes, last_page)
      last_page = page  
      pages["other_nodes"]=page
      # add the interogation logic
      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]
      #fetch_reference(all_nodes)  
      build_relevance(all_nodes, age_node, js_nodes) 
      
      #fetch_condition(all_nodes,js_nodes)
      ## add the diagnostics
      
      page = create_activity(list(js_diagnoses.keys()), "diagnoses", media_path, js_diagnoses, last_page)    
      last_page = page  
      pages["diagnoses"]=page
      prefix = 'qual'
      #all_nodes = [*page.nodes, age_node, brith_date_node]
      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]

      #fetch_reference(all_nodes,prefix=prefix)
      build_relevance(all_nodes, age_node, js_nodes,prefix=prefix) 
      #fetch_condition(all_nodes,js_nodes,prefix=prefix)
      ## add the diagnostics
      
      prefix = 'diag'
      page = create_activity(list(js_final_diagnoses.keys()), "final_diagnoses", media_path, js_final_diagnoses, last_page)    
      last_page = page  
      pages["final_diagnoses"]=page

      #all_nodes = [*page.nodes, age_node, brith_date_node]
      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]

      #fetch_reference(all_nodes,prefix=prefix)
      build_relevance(all_nodes, age_node, js_diagnoses,prefix=prefix) 
      #fetch_condition(all_nodes,js_diagnoses,prefix=prefix)



      all_nodes = [node for page in list(pages.values()) for node in page.nodes ]
      all_group = [group for page in list(pages.values()) for group in page.groups ]
      
    


                            

      ## all logic
  #   all_nodes.extend([age_node,yi_node,child_node])
      
      older_groups =  list(filter(lambda gp: gp.name == 'older', all_group))
      yi_groups =  list(filter(lambda gp: gp.name == 'neonat', all_group))


      for gp in older_groups:
          set_prev_next_node(child_node,gp)
      for gp in yi_groups:
          set_prev_next_node(yi_node,gp)
          
      for page in pages.values():
        for node in page.nodes:
          if len(node.prev_nodes)==0 and len(node.next_nodes)==0:
            page.nodes.remove(node)
          
      return start_page, pages     
          
      