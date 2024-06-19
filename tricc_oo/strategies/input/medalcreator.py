
import json
from types import SimpleNamespace

from tricc_oo.converters.mc_to_tricc import (
  create_activity,build_relevance,
  get_registration_nodes,
  add_age_calcualte_nodes,
  add_background_calculations,
  add_qd_dd_nodes,
  build_calculations,
  unloop_queston,
  )
from tricc_oo.models import *
from tricc_oo.visitors.tricc import set_prev_next_node
from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy

media_path = "./"
class MedalCStrategy(BaseInputStrategy):
  def execute(self, in_filepath, media_path):
      #load all
      f = open(in_filepath)
      js_full = json.load(f)
      pages = {}
      start_page= {}
      # Get the order
      js_fullorder =  js_full['medal_r_json']['config']['full_order']
      # get the nodes
      js_nodes = js_full['medal_r_json']['nodes']
      
      js_final_diagnoses = js_full['medal_r_json']['final_diagnoses']
      js_diagnoses = js_full['medal_r_json']['diagnoses']
      #js_diagrams = js_full['medal_r_json']['diagram']
      js_qs_id = [ id for id ,node in js_nodes.items() if node['type'] == "QuestionsSequence" ]
      #get the special question
      weight_id = js_full['medal_r_json']['config']['basic_questions']['weight_question_id']
      gender_id = js_full['medal_r_json']['config']['basic_questions']['gender_question_id']
      
      yi_cc_id = js_full['medal_r_json']['config']['basic_questions']['general_cc_id']
      child_cc_id = js_full['medal_r_json']['config']['basic_questions']['yi_general_cc_id']
      js_trad = js_full['medal_r_json']['config']['systems_translations']
      #TODO manage village list for village questions
      # add patietn nodes
      js_registration_nodes = get_registration_nodes()   
      # create diagnose pages
      # that are all merged and splitted in stages
      js_questions = {**js_registration_nodes, **js_nodes}
      is_first=True
      last_page = None
      #TODO, dont male any link
      for key, stage in js_fullorder.items():
          page = create_activity(stage, key, media_path, js_questions, last_page, js_trad)
          if is_first :
              start_page['main'] = page
              page.root.form_id=js_full['id']
              page.root.label=js_full['name']
          else:
              set_prev_next_node(start_page['main'].root, page)
          is_first = False
          last_page = page  
          pages[key]=page
      all_nodes = update_all_nodes(pages)
      # enrich with other nodes
      
      age = add_age_calcualte_nodes(all_nodes)

      add_background_calculations(start_page['main'], pages, js_nodes, all_nodes)
      add_qd_dd_nodes(start_page['main'], pages, age, js_nodes,js_diagnoses, all_nodes)
      #create the actual calculation (cannot be done in add_background_calculations because not all nodes are created)
      build_calculations(start_page, pages, js_nodes, all_nodes)
      
      all_nodes = update_all_nodes(pages)

      #add trigger for the CC questions
      js_nodes[str(yi_cc_id)]["cut_off_end"] = 62
      js_nodes[str(child_cc_id)]["cut_off_start"] = 62
      # create relevance and prev/next based on relevance
      build_relevance(all_nodes, age, js_questions, js_diagnoses, js_final_diagnoses)
      

      unloop_queston(start_page['main'], pages, age, js_nodes,js_diagnoses, all_nodes)


      # all_nodes = [node for page in list(pages.values()) for node in page.nodes ]
      # all_group = [group for page in list(pages.values()) for group in page.groups ]
            
      # older_groups =  list(filter(lambda gp: gp.name == 'older', all_group))
      # yi_groups =  list(filter(lambda gp: gp.name == 'neonat', all_group))
        
      #cleaning
      for page in pages.values():
        to_del=[]
        for node in page.nodes.values():
          if len(node.prev_nodes)==0 and len(node.next_nodes)==0:
            to_del.append(node.id) 
        for id in to_del:
              del page.nodes[id]
          
      return start_page, pages     
          
def update_all_nodes(pages):
  all_nodes={}
  for page in pages.values():
    for node in page.nodes.values():
      all_nodes[node.id] = node
    for node in page.calculates:
      all_nodes[node.id] = node
  
  return all_nodes