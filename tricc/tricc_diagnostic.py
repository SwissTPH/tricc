#!/usr/bin/env python
# coding: utf-8

# In[1087]:


from lxml import etree
import pandas as pd
import networkx as nx
import html
from xml.sax.saxutils import unescape
import hashlib
import re
import numpy as np
import os
import base64 # to extract images from base64 strings (as they are stored in xml files)
from datetime import datetime
import html2text


# In[1088]:


# parsing xml file

file='eCARE_ped_diagnostic-newskin.drawio'
output_file='msfecare_ped.xlsx'
form_id='msfecare_ped'
treatment_flow=False

# reads the whole file and 'data' is a wrapper for the entire tree
data = etree.parse(file)

# gets the name of the highest element of the tree and puts it into the variable 'root'
root = data.getroot()

# find the element that has the tag 'root' BELOW the 'root' one
objects = root.find('.//root')

# as before for the 'root' element, here we get a list of all child-elements of the 'diagram' element (recursively)
# objects_elements=list(objects.iter())

# same again but find only elements with 'mxCell' tag
#objects_elements=list(objects.iter('mxCell'))
objects_elements=list(objects.findall('mxCell'))

# find other tags that also contain relevant data
objects_elements.extend(list(objects.findall('UserObject')))
objects_elements.extend(list(objects.findall('object')))


# In[1089]:


# putting content of xml into dataframe df

#df = pd.DataFrame(columns=['tag','id', 'value', 'style', 'xml-parent','source','target','name','media'])
rows=[]

for item in objects_elements:
    if item.tag=='mxCell':
        row = list([item.tag,item.attrib.get('id'),item.attrib.get('value'),item.attrib.get('label'),item.attrib.get('style'),
                    item.attrib.get('parent'),item.attrib.get('source'),item.attrib.get('target'),item.attrib.get('name'),
                    item.attrib.get('odk_type'),item.attrib.get('min'),item.attrib.get('max'),
                    item.attrib.get('required'),item.attrib.get('constraint_message'),''])
    if item.tag=='UserObject':
        nested_mxCell=item.find('.//mxCell')
        row = list([item.tag,item.attrib.get('id'),nested_mxCell.attrib.get('value'),item.attrib.get('label'),
                    nested_mxCell.attrib.get('style'),nested_mxCell.attrib.get('parent'),
                    item.attrib.get('source'),item.attrib.get('target'),
                    item.attrib.get('name'),item.attrib.get('odk_type'),item.attrib.get('min'),item.attrib.get('max'),
                    item.attrib.get('required'),item.attrib.get('constraint_message'),''])
    if item.tag=='object':
        nested_mxCell=item.find('.//mxCell')
        row = list([item.tag,item.attrib.get('id'),item.attrib.get('label'),item.attrib.get('label'),
                    nested_mxCell.attrib.get('style'),nested_mxCell.attrib.get('parent'),
                    item.attrib.get('source'),item.attrib.get('target'),
                    item.attrib.get('name'),item.attrib.get('odk_type'),item.attrib.get('min'),item.attrib.get('max'),
                    item.attrib.get('required'),item.attrib.get('constraint_message'),''])
    rows.append(row)

df=pd.DataFrame(rows,columns=
                ['tag','id','value','label_userObject', 'style', 'xml-parent','source','target','name','odk_type',\
                 'min','max','required','constraint_message','media'])

df.loc[df.tag=='UserObject','value']=df.label_userObject


# In[1090]:


# make a constraint column
df['constraint']=''
df.loc[df['min'].notna(),'constraint']='.>=' + df['min']
df.loc[df['max'].notna(),'constraint']=df['constraint'] + ' and .<=' + df['max']
df.drop(columns=['min','max'],inplace=True)


# In[1091]:


# unescape converts codings like &lt into <. 
# in the xml file html needs to be encoded like that, otherwise it would interfere with the coding of the xml file

# the soup.text strips off the html formatting also
def remove_html(str):
    text = html2text.html2text(str) # retrive pure text from html
    text = text.strip('\n') # get rid of empty lines at the end (and beginning)
    text = text.split('\n') # split string into a list at new lines
    text = '\n'.join([i.strip(' ') for i in text if i]) # in each element in that list strip empty space (at the end of line) 
    # and delete empty lines
    return text

# remove html formatting and keep text inside rhombus
df.loc[df['odk_type']=='rhombus','value'] = df.loc[df['odk_type']=='rhombus','value'].apply(lambda x: remove_html(x) if x!=None else None)
# remove html formatting in questions (not allowed here)
df.loc[df['odk_type'].str.contains('select_',na=False),'value'] = df.loc[df['odk_type'].str.contains('select_',na=False),'value'].apply(lambda x: remove_html(x) if x!=None else None)
# remove also in decimal and integer
df.loc[df['odk_type']=='decimal','value'] = df.loc[df['odk_type']=='decimal','value'].apply(lambda x: remove_html(x) if x!=None else None)
df.loc[df['odk_type']=='integer','value'] = df.loc[df['odk_type']=='integer','value'].apply(lambda x: remove_html(x) if x!=None else None)
df.loc[df['odk_type']=='calculate','value'] = df.loc[df['odk_type']=='calculate','value'].apply(lambda x: remove_html(x) if x!=None else None)


# remove all html from 'value column' when dealing with the high flow of treatments
if treatment_flow:
    df['value'] = df['value'].apply(lambda x: remove_html(x) if x!=None else None)
    df['label_userObject'] = df['label_userObject'].apply(lambda x: remove_html(x) if x!=None else None)


# In[1092]:



# where 'name' empty, use generic hash ID
#df.loc[df['name'].isna(),'name']=df['id'].apply(lambda x: hashlib.sha1(x.encode()).hexdigest())
df.loc[df['name'].isna(),'name']=df['id']
# where duplicates (for instance default name for a text message is 'label_'; if user does not change it remains the same)
# ATTENTION: if you select duplicates first and in second step it does not base on the duplicates but on the entire dataframe
# this took time to solve, also filtering with 'name' did not work, had to use the same column in both conditions: 'name'
# this should not be applied to select_options and to rhombus, because those can have duplicates.
df.loc[df.duplicated(subset=['name'],keep=False) & ~df['name'].str.contains('opt_',na=False)        & ~df['name'].str.contains('stored_',na=False),'name']=df['name']+df['id']

df.set_index('id',inplace=True)

df['Number of outgoing arrows']=df['source'].value_counts()
df['Number of incoming arrows']=df['target'].value_counts()
df['Number of outgoing arrows'].fillna(0,inplace=True)
df['Number of incoming arrows'].fillna(0,inplace=True)

# replace NaN with empty strings
df.value.fillna('',inplace=True)

# deal with duplicates
#c=0
#for index, elem in df.loc[df['name'].duplicated()].iterrows():
#    df.loc[index,'name'] = df.loc[index,'name']+str(c)
#    c+=1    

# df.tail()


# In[1093]:


# make a dataframe with connectors only
df_arrows=df.loc[df.source.notna() & df.target.notna(),['source','target','value']]

# drop arrows from df
df.drop(df_arrows.index,inplace=True)

df_arrows.head()


# In[1094]:


# creating a folder for images and other media

if not(os.path.isdir('media')): # check if it exists, because if it does, error will be raised 
    # (later change to make folder complaint to CHT)
    os.mkdir('media')


# In[1095]:


# finding png images that belong to container-hint-media (not included are those that belong to select_options)
df.loc[df['style'].str.contains("image/png",na=False),'odk_type']='png-image'+df.name+'.png'

# getting a dataframe with png-images only (better for joining with df later)
# images:rows where 'xml-parent' is inside the index of rows that have the entry 'container_hint_media' in odk_type column, 
# of those rows we extract those where the 'type' column contains the substring 'png-image'
# and of the result we just take the columns 'xml-parent', 'odk_type' and 'style'
# 'xml-parent' is the container it belongs to and the line that will contain the info about the image
# 'odk_type' contains also the file name .png
# 'style' contains the actual image data

df_png=df.loc[df['xml-parent'].isin(df.loc[df['odk_type']=='container_hint_media'].index) 
              & df['odk_type'].str.contains('png-image',na=False),
              ['xml-parent','odk_type','style']] # images that are in 'containers_hint_media'

# getting image data from 'style' column for all images (from containers AND select_options) and storing it to disk
df_pngAll=df.loc[df['odk_type'].str.contains('png-image',na=False),['xml-parent','odk_type','style']]
for index, row in df_pngAll.iterrows():
    string = row['style'] 
    img_data=re.search('image/png,(.+?);',string).group(1) # extract image data from 'style' column using regex
    with open('media/'+row['odk_type'], "wb") as fh:
        fh.write(base64.decodebytes(img_data.encode('ascii'))) # encode image into ascii (binary) and save

df_png.rename({'xml-parent':'container_id','odk_type':'media::image::English (en)'},axis=1,inplace=True)
index_delete=df_png.index
df_png.set_index('container_id',inplace=True)
df_png.drop('style',axis=1,inplace=True)

# joinging df and df_png (this adds the media-image column to df)
df=df.join(df_png)

# remove the rows with those 'png messages' in df as they are no longer needed
df.drop(index_delete,inplace=True)

df.loc[df['media::image::English (en)'].notna()].head()


# In[1096]:


# finding jpeg images that belong to container-hint-media (not included are those that belong to select_options)
df.loc[df['style'].str.contains("image/jpeg",na=False),'odk_type']='jpeg-image'+df.name+'.jpeg'

# getting a dataframe with png-images only (better for joining with df later)
# images:rows where 'xml-parent' is inside the index of rows that have the entry 'container_hint_media' in odk_type column, 
# of those rows we extract those where the 'type' column contains the substring 'png-image'
# and of the result we just take the columns 'xml-parent', 'odk_type' and 'style'
# 'xml-parent' is the container it belongs to and the line that will contain the info about the image
# 'odk_type' contains also the file name .png
# 'style' contains the actual image data

df_png=df.loc[df['xml-parent'].isin(df.loc[df['odk_type']=='container_hint_media'].index) 
              & df['odk_type'].str.contains('jpeg-image',na=False),
              ['xml-parent','odk_type','style']] # images that are in 'containers_hint_media'

# getting image data from 'style' column for all images (from containers AND select_options) and storing it to disk
df_pngAll=df.loc[df['odk_type'].str.contains('jpeg-image',na=False),['xml-parent','odk_type','style']]
for index, row in df_pngAll.iterrows():
    string = row['style'] 
    img_data=re.search('image/jpeg,(.+?);',string).group(1) # extract image data from 'style' column using regex
    with open('media/'+row['odk_type'], "wb") as fh:
        fh.write(base64.decodebytes(img_data.encode('ascii'))) # encode image into ascii (binary) and save

df_png.rename({'xml-parent':'container_id','odk_type':'media::image::English (en)'},axis=1,inplace=True)
index_delete=df_png.index
df_png.set_index('container_id',inplace=True)
df_png.drop('style',axis=1,inplace=True)

# joinging df and df_png (this adds the media-image column to df)
#df=df.join(df_png)
df.update(df_png)

# remove the rows with those 'png messages' in df as they are no longer needed
df.drop(index_delete,inplace=True)

df.loc[df['media::image::English (en)'].notna()].head()


# In[1097]:


# getting an dataframe with HINT-images only (better for joining later)
# hints are grey boxes inside a container
# hints:rows where 'xml-parent' is inside the index of rows that have the entry 'container_hint_media' in type column, 
# of those rows we extract those where the 'style' column contains the substring 'fillColor=#f5f5f5' (grey backgroud)
# and of the result we just take the columns 'xml-parent' and 'type'
df_hint=df.loc[df['xml-parent'].isin(df.loc[df.odk_type=='container_hint_media'].index) & df['style'].str.contains('fillColor=#f5f5f5',na=False),['xml-parent','value']]
df_hint.rename({'xml-parent':'container_id','value':'hint::English (en)'},axis=1,inplace=True)
index_delete=df_hint.index
df_hint.set_index('container_id',inplace=True)

# joining df and df_hint (this adds the hint message column to df)
df=df.join(df_hint)

# remove the rows with 'hint messages' in df as they are no longer needed
df.drop(index_delete,inplace=True)

df.loc[df['hint::English (en)'].notna()].head()


# In[1098]:


# getting an dataframe with Help-images only (better for joining later)
# hints are grey boxes inside a container
# hints:rows where 'xml-parent' is inside the index of rows that have the entry 'container_hint_media' in type column, 
# of those rows we extract those where the 'style' column contains the substring 'fillColor=#f5f5f5' (grey backgroud)
# and of the result we just take the columns 'xml-parent' and 'type'
df_help=df.loc[df['xml-parent'].isin(df.loc[df.odk_type=='container_hint_media'].index) & (df['odk_type']=='help_message'),['xml-parent','value']]
df_help.rename({'xml-parent':'container_id','value':'help::English (en)'},axis=1,inplace=True)
index_delete=df_help.index
df_help.set_index('container_id',inplace=True)

# joining df and df_help (this adds the hint message column to df)
df=df.join(df_help)

# remove the rows with 'hint messages' in df as they are no longer needed
df.drop(index_delete,inplace=True)

df.loc[df['help::English (en)'].notna()].head()


# In[1099]:


# make a dataframe that will be needed later to replace sources in df_arrows which are inside a container, by the container itself

df_new_arrow_sources = df.loc[df['xml-parent'].isin(df.loc[df.odk_type=='container_hint_media'].index) 
                              | df['xml-parent'].isin(df.loc[df.odk_type=='container_page'].index),['xml-parent','odk_type']]
df_new_arrow_sources.rename({'xml-parent':'container_id','odk_type':'odk_type_of_content'},axis=1,inplace=True)

# add also the type of the container (page or hint-image)
df_new_arrow_sources = df_new_arrow_sources.merge(df[['odk_type']],how='left',left_on='container_id',right_index=True)


# In[1100]:


# getting an dataframe with text cells inside the containers only (better for joining later)
# text-cells:rows where 'xml-parent' is inside the index of rows that have the entry 'container_hint_media' in type column, 
# of those rows we extract those where the 'style' column NOT contains the substring 'png-image' 
# and NOT contains the substring 'fillColor=#f5f5f5' in style (these are grey background objects that are reserved for hints)
# and of the result we just take the columns 'xml-parent' and 'type'
df_label=df.loc[df['xml-parent'].isin(df.loc[df.odk_type=='container_hint_media'].index) 
                & ~df['odk_type'].str.contains('png-image',na=False) 
                & ~df['style'].str.contains('fillColor=#f5f5f5',na=False),['xml-parent','value','odk_type','name']]
df_label.rename({'xml-parent':'container_id','value':'value_label'},axis=1,inplace=True)
index_delete=df_label.index
df_label.set_index('container_id',inplace=True)

# deleting elements in the 'value' column of all container rows 
# (normally these should be empty already, but you never know if the user adds a heading to the container)
df.loc[df.index.isin(df_label.index),'value']=''

# replacing 'odk_type' value of the container row in df with the one from df_label (because this is where the info is stored) 
df['odk_type'].update(df_label['odk_type'])
# replacing 'name' value of the container row in df with the one from df_label (because this is where the info is stored) 
df['name'].update(df_label['name'])

#deleting the columns 'odk_type' and 'name' from df_label because it would raise error in join in the next step
df_label.drop(['odk_type','name'],axis=1,inplace=True)

# joining df and df_label (this adds the column 'value_label' to df)
df=df.join(df_label)
# the elements in the created column 'value_label' that do not belong to containers are now NaN
# need to converted to empty strings if we want to combine 'value' and 'value_label'
df.value_label.fillna('',inplace=True)

# combining the two columns 'value' and 'value_label'
df['value']=df['value']+df['value_label'].astype(str)

# deleting the 'value_label' column that is no longer needed
df.drop('value_label',axis=1,inplace=True)

# remove the rows with 'labels messages from containers' in df as they are no longer needed
df.drop(index_delete,inplace=True)

# df.loc[df['hint::English (en)'].notna() | df['media::image::English (en)'].notna() | df['help::English (en)'].notna()].head()


# In[1101]:


# for connectors where the source is inside a container-hint-media, replace the source with the container itself
df_hint_media_objects = df_new_arrow_sources.loc[df_new_arrow_sources['odk_type']=='container_hint_media']
df_arrows = df_arrows.merge(df_hint_media_objects,how='left',left_on='source',right_index=True)
df_arrows.rename(columns={'odk_type':'container_type'},inplace=True)
m=(df_arrows['container_type']=='container_hint_media')
df_arrows.loc[m,'source']=df_arrows.loc[m,'container_id']
df_arrows.loc[m,'source_type']=df_arrows.loc[m,'odk_type_of_content']
df_arrows.drop(columns=['container_id','odk_type_of_content','container_type'],inplace=True)
df_arrows.fillna('',inplace=True)


# In[1102]:


# giving rhombus a 'odk_type'
df.loc[df['style'].str.contains("rhombus",na=False),'odk_type']='rhombus'

# making a dataframe with all choice options for all valueSets (choices tab)
# all elements whose 'xml-parent' is the 'id' of elements that have 'select_xxx' in type
# these are all options (elements of valuesets)
df_choices=df.loc[df['odk_type']=='select_option']
df_choices=df_choices.merge(df[['name','odk_type']],how='left',left_on='xml-parent',right_index=True)
df_choices=df_choices[['name_y','name_x','value','odk_type_y']]

# info: the 'odk_type' is kept because it will be necessary for making the logic (relevant column)
df_choices.rename({'name_y':'list_name','name_x':'name','value':'label::English (en)','odk_type_y':'odk_type'},axis=1,inplace=True)

# remove the rows with 'choices' in df as they are no longer needed
df.drop(df_choices.index,inplace=True)

# make a dataframe that contains only remaining image objects (those that belong to options)
df_png = df.loc[df['odk_type'].str.contains('-image',na=False),'odk_type'].to_frame()
# drop the select_option images from df
df.drop(df_png.index)
# merge with df_arrows to add the 
df_png = df_png.merge(df_arrows[['source','target']],how='left',left_index=True,right_on='source')
df_png.rename(columns={'odk_type':'media::image::English (en)'},inplace=True)
# add the image name to df_choices
df_choices = df_choices.reset_index().merge(df_png[['media::image::English (en)','target']],                                            how='left',left_on='id',right_on='target').set_index('id')
# drop the target column
df_choices.drop(columns=['target'],inplace=True)

# drop the remaining unspecified objects (pure xml formating related elements or drawing artefacts) 
df.drop(df.loc[df.value==''].index,inplace=True)

# add rows for yesno
yes=['yesno','Yes','Yes','select_one','']
no=['yesno','No','No','select_one','']
df_choices.loc['zzz_yes']=yes
df_choices.loc['zzz_no']=no


# In[1103]:


# preparing df_arrows for logic part:

# rename index of df_arrows to reduce confusion
df_arrows.index.rename('Arrow ID',inplace=True)

# make a logical expression for each arrow

# add names of the source from df (for the case when the source is NOT a select_xxx) (names are the odk id's)
# the value is only needed for the rhombus

'''
First we merge with df and then again with df_choices. The reason for that: at this stage, 
the arrows originate from select_xxx options (opt1,opt2,...), but do not point to them. 
However, at a later stage, those arrows are modified so they originate from the select_xxx itself. If that step was done 
before, we would not need to have to merge twice here. When improving the form builder, consider changing this. 
'''
# merging with df to get the odk_type
df_arrows=df_arrows.merge(df[['name','odk_type']],how='left',left_on='source',right_index=True)
# moving the type of the source into the column 'source_type'
df_arrows.loc[df_arrows['source_type']=='','source_type']=df_arrows.loc[df_arrows['source_type']=='','odk_type']
# droping the 'odk_type' column, it is no longer needed
df_arrows.drop(columns=['odk_type'],inplace=True)
df_arrows.fillna('',inplace=True)

# merging with df_choices to get the odk_type for when the source is a select_xxx
df_arrows=df_arrows.merge(df_choices[['list_name','name','odk_type']],how='left',left_on='source',right_index=True)
# as before for df, moving the type of the source into the column 'source_type'
df_arrows.loc[df_arrows['source_type']=='','source_type']=df_arrows.loc[df_arrows['source_type']=='','odk_type']
df_arrows.fillna('',inplace=True)

# merge names from df and df_choices into one column
df_arrows['source_name']=df_arrows['name_x']+df_arrows['list_name']
df_arrows.drop(['name_x','list_name','odk_type'],axis=1,inplace=True)
df_arrows.rename(columns={'name_y':'select_option'},inplace=True)


# In[1104]:


df_arrows['expression']=''

# add connectors to virtual objects (loaded objects)

# expression for yes no questions
df_arrows.loc[df_arrows['source_type']=='select_one yesno','expression'] = '${'+df_arrows['source_name'] + '}=' + '\'' + df_arrows.value + '\''

# expression for integers and decimals
df_arrows.loc[(df_arrows['source_type']=='integer') | (df_arrows['source_type']=='decimal'),'expression'] = '${'+df_arrows['source_name'] + '}!=' + '\'\''

# expression for all the other select_one
df_arrows.loc[df_arrows['source_type']=='select_one','expression'] = '${'+df_arrows['source_name'] + '}=' + '\'' + df_arrows['select_option'] + '\''

# expression for select_multiple
df_arrows.loc[df_arrows['source_type']=='select_multiple','expression'] = 'selected(${'+df_arrows['source_name'] + '},\'' + df_arrows['select_option'] + '\')'

# expression for source being a calculate
df_arrows.loc[df_arrows['source_type']=='calculate','expression'] = '${'+df_arrows['source_name'] + '}=1'


# In[1105]:


# expression for target being a count---> in this case the expression depends not on the source but on the target!
counters=df.loc[df['odk_type']=='count'].index
m = df_arrows['target'].isin(df.loc[df['odk_type']=='count'].index) # mask for connectors that point to 'count' objects
df_arrows.loc[m,'expression'] = 'number(' + df_arrows.loc[m,'expression'] + ')'

# for counters you must combine the expression of all icoming arrows into the one expression of that counter. 
# from there on, a rhombus, referring to a counter can lookup the entire expression


# In[1106]:


# expression for rhombus

# first get the 'odk_type' of the object that the rhombus is refering to

# strip of 'stored_' from the rhombus source_name
df_arrows.loc[df_arrows['source_type']=='rhombus','source_name'] = df_arrows.loc[df_arrows['source_type']=='rhombus','source_name'].apply(lambda x : x.replace('stored_',''))

# look up the odk_type that the rhombus is refering to
df_arrows = df_arrows.merge(df[['odk_type','name']],how='left',left_on='source_name',right_on='name')
# get rid of the 'name' column (was just needed for merging) and rename 'odk_type' column, to avoid confusion
df_arrows.drop('name',axis=1,inplace=True)
df_arrows.rename(columns={'odk_type':'rhombus_refer_to_odk_type'},inplace=True)

# look up the value of the rhombus, it contains info about the logic
df_arrows = df_arrows.merge(df[['value']],how='left',left_on='source',right_index=True)
df_arrows.rename(columns={'value_x':'value','value_y':'value_of_rhombus'},inplace=True)
# set all 'NaN' to empty strings
df_arrows=df_arrows.fillna('')


# In[1107]:


# when rhombus refers to a an integer or decimal
m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type'].isin(['integer','decimal']))
df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.replace(r'^[^<=>]+','',regex=True) # only keep what comes after <,= or >
df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.replace('?','',regex=False) # remove the '?' at the end
df_arrows.loc[m,'expression'] = '${'+df_arrows['source_name'] + '}' + df_arrows['value_of_rhombus']
df_arrows.loc[m & (df_arrows['value']=='No')] = df_arrows.loc[m & (df_arrows['value']=='No')].replace({'<=':'>','>=':'<','<':'>=','>':'<='},regex=True)

# when rhombus refers to a select_one yesno
m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type']=='select_one yesno')
df_arrows.loc[m,'expression'] = '${'+df_arrows['source_name'] + '}=' + '\'' + df_arrows.value + '\''

# this is very specific for MSFeCARE where the age is a select_one, but then there are rhombus refering to it as if it was 
# an integer!!! Must do this like that in the short run, but a better fix is needed in the future. ----> MAKE THIS WORK AT SOME POINT!!! disabled for now, the TRICC drawing is adapted accordingly
#m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type']=='select_one') & (df_arrows['source_name']=='p_age')
#df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.replace(r'^[^<=>]+','',regex=True) # only keep what comes after <,= or >
#df_arrows.loc[m,'expression'] = '${'+df_arrows['source_name'] + '}' + df_arrows['value_of_rhombus']

# now the real select_ones:
# m = (df_arrows['source_type']=='rhombus') & df_arrows['rhombus_refer_to_odk_type'].str.contains('select_',na=False) & (df_arrows['source_name']!='p_age')
m = (df_arrows['source_type']=='rhombus') & df_arrows['rhombus_refer_to_odk_type'].str.contains('select_',na=False) & (df_arrows['rhombus_refer_to_odk_type']!='select_one yesno')
df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.extract(r'\[(.*?)\]',expand=False)
# merge again with df_choices to get the 'name' of the selected option (also needed for select_multiple!)
df_arrows = df_arrows.merge(df_choices[['list_name','name','label::English (en)']],                 how='left',left_on=['source_name','value_of_rhombus'],right_on=['list_name','label::English (en)'])
# when the outgoing arrow is YES (means that what is in RHOMBUS is TRUE)
df_arrows.loc[m & (df_arrows['value']=='Yes'),'expression'] =  '${'+df_arrows['source_name'] + '}=' + '\'' + df_arrows['name'] + '\''
# when the outgoing arrow is NO (means that what is in RHOMBUS is FALSE)
df_arrows.loc[m & (df_arrows['value']=='No'),'expression'] =  '${'+df_arrows['source_name'] + '}!=' + '\'' + df_arrows['name'] + '\''

# when rhombus refers to select_multiple
#m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type']=='select_multiple')
#df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.extract(r'\[(.*?)\]',expand=False)
# when the outgoing arrow is YES (means that what is in RHOMBUS is TRUE)
df_arrows.loc[m & (df_arrows['value']=='Yes'),'expression'] = 'selected(${'+df_arrows['source_name'] + '},\'' + df_arrows['name'] + '\')'
# when the outgoing arrow is NO (means that what is in RHOMBUS is FALSE)
df_arrows.loc[m & (df_arrows['value']=='No'),'expression'] = 'not(selected(${'+df_arrows['source_name'] + '},\'' + df_arrows['name'] + '\'))'


# In[1108]:


# when rhombus refers to calculate
m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type']=='calculate')
# when the outgoing arrow is YES (means that what is in RHOMBUS is TRUE)
df_arrows.loc[m & (df_arrows['value']=='Yes'),'expression'] = '${'+df_arrows['source_name'] + '}=1'
# when the outgoing arrow is NO (means that what is in RHOMBUS is False)
df_arrows.loc[m & (df_arrows['value']=='No'),'expression'] = '${'+df_arrows['source_name'] + '}=0'


# In[1109]:


# when rhombus refers to a count (in this case we must combine all 'expressions' of the incoming arrows into the count object 
# with ' + ') and put the result into the 'expression' of the rhombus that is refering to it
m = (df_arrows['source_type']=='rhombus') & (df_arrows['rhombus_refer_to_odk_type']=='count')
df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.replace(r'^[^<=>]+','',regex=True) # only keep what comes after <,= or >
df_arrows.loc[m,'value_of_rhombus'] = df_arrows.loc[m,'value_of_rhombus'].str.replace('?','',regex=False) # remove the '?' at the end

# new mask to get the df_arrows of all connectors that point to counters
m1 = df_arrows['target'].isin(df.loc[df['odk_type']=='count'].index) # mask for connectors that point to 'count' objects
gk = df_arrows.loc[m1].groupby('target') # group them by counters

for elem, group in gk:
    # for each counter (elem), combine the expressions of all incoming arrows into a single one, concatenated with +
    full_expression=' + '.join(filter(None,group['expression']))
    # put result into brackets, because comparison is executed BEFORE +
    full_expression = '(' + full_expression + ')'
    
    # lookup the 'name' of the counter in df, based on the id = target
    counter_name = df.loc[elem,'name']
    
    # check in df_arrows where the 'counter_name' is
    df_arrows.loc[m & (df_arrows['source_name']==counter_name),'expression'] = full_expression + df_arrows['value_of_rhombus']
    
    # for the 'No' arrow we invert > and <
    df_arrows.loc[m & (df_arrows['source_name']==counter_name) & (df_arrows['value']=='No'),'expression'] = df_arrows.loc[m & (df_arrows['source_name']==counter_name) & (df_arrows['value']=='No'),'expression'].replace({'<=':'>','>=':'<','<':'>=','>':'<='},regex=True)


# In[1110]:


# also drop the arrows that point to counters
df_arrows = df_arrows[df_arrows['target'].isin(df.loc[df['odk_type']!='count'].index)]

# drop no longer necessary columns
df_arrows.drop(columns=['value','value_of_rhombus','source_name','rhombus_refer_to_odk_type','list_name','label::English (en)','name'],inplace=True)

# also drop count objects from df, they are no longer needed
df.drop(df[df['odk_type']=='count'].index,inplace=True)


# In[1111]:


'''A rhombus can refer to a field that is not in the drawing. For instance, in the TT flow, where values like fever are used
but not calculated. Or in CHT, when patient info or hospital info is loaded into the input section. 
For this, the symbols are drawn in the beginning of the flow, pointing to the note field 'Load Data'. 
Once this is done, it is handled correctly by the script and they get included. '''


# In[1112]:


# modifying the sources of select_options:
# Where the source is a select_xxx option, replace it with the select_xxx itself 
# (that is because the options are dead ends when walking down the tree)

# merge df_arrows with df_choices
df_arrows = df_arrows.merge(df_choices[['list_name']],how='left', left_on='source', right_index=True)
# replace NaN with empty strings
df_arrows['list_name'].fillna('',inplace=True)

# merge the new df_arrows with df:
df_arrows = df_arrows.merge(df.reset_index()[['id','name']],how='left',left_on='list_name',right_on='name')

# make a mask for all rows with source type select_xxx
m_select = df_arrows['source_type'].isin(['select_multiple','select_one'])
df_arrows.loc[m_select,'source']=df_arrows.loc[m_select,'id']

df_arrows.drop(columns=['list_name','id','name'],inplace=True)


# In[1113]:


# for connectors where the source is inside a container-hint-media, replace the source with the container itself
df_arrows = df_arrows.merge(df_new_arrow_sources,how='left',left_on='source',right_index=True)
df_arrows.fillna('',inplace=True)
df_arrows.rename(columns={'odk_type':'container_type'},inplace=True)
m=(df_arrows['container_type']=='container_hint_media')
df_arrows.loc[m,'source']=df_arrows.loc[m,'container_id']
df_arrows.loc[m,'source_type']=df_arrows.loc[m,'odk_type_of_content']


# In[1114]:


# get container_ids of pages
container_ids = df_arrows.loc[df_arrows['container_type']=='container_page','container_id'].unique()

# the ids of objects which are inside the page - containers
page_objects = df.loc[df['xml-parent'].isin(container_ids)].index

# get those page_objects which are the starting point of the flow INSIDE the page
page_starts = page_objects[~page_objects.isin(df_arrows['target'])]

# get the page_starts that are a rhombus (needed for later)
page_starts_rhombus = df.loc[page_starts].loc[df['odk_type']=='rhombus'].index

# get the page_objects where all objects in a single page are notes (needed for later)

# get page_start - container_id pairs
dfnew_connectors = df.loc[page_starts,['xml-parent']].reset_index().rename(columns={'id':'target','xml-parent':'source'})

# add missing columns
dfnew_connectors = dfnew_connectors.reindex(columns=['source','target','source_type','expression','container_id','container_type'])
dfnew_connectors['source_type']='page'
dfnew_connectors.fillna('',inplace=True)

# concat that to df_arrows
df_arrows = pd.concat([df_arrows,dfnew_connectors])

# adding 'target_type' to df_arrows
df_arrows = df_arrows.merge(df['odk_type'],how='left',left_on='target',right_index=True)
df_arrows.rename(columns={'odk_type':'target_type'},inplace=True)


# In[1115]:


# all connectors are present, we build the graph with networkx

# make a topological sort of objects in df (so that the order of questions in the flow is correct)

# make a directed graph 
dg = nx.from_pandas_edgelist(df_arrows, source='source', target='target', create_using=nx.DiGraph)
order = list(nx.lexicographical_topological_sort(dg))

# change order of rows
df=df.reindex(order)


# In[1116]:


# This is necessary because there are pure note pages. In this case notes that point ouf of the page, have no 'expression'
# and this interrupts the flow. The solution is to give those 'notes' as expression the 'relevant' of the page, while 
# building the logic

df_pageObjects = df.loc[df['xml-parent'].isin(df.loc[df['odk_type']=='container_page'].index)]

# get ids of pages that ONLY contain 'notes'
pure_note_pages=[]
gk = df_pageObjects.groupby('xml-parent')
for elem,frame in gk: 
    if len(frame.index) == len(frame.loc[frame['odk_type']=='note']):
        pure_note_pages.append(elem)

# get all the 'notes' that point out pages:
df_notes_out_pages = df_arrows.loc[df_arrows['source'].isin(df_pageObjects.index) &                                     ~df_arrows['target'].isin(df_pageObjects.index) & (df_arrows['source_type']=='note')]

# among those get those notes that belong to 'pure_note_pages' - these are the notes you are looking for
df_notes_outof_pure_notes_pages = df_notes_out_pages.loc[df_notes_out_pages['container_id'].isin(pure_note_pages)]
df_notes_outof_pure_notes_pages = df_notes_outof_pure_notes_pages[['source','container_id']]
df_notes_outof_pure_notes_pages.set_index('source',inplace=True)


# In[1117]:


'''
Building the logic: 
1. It must be done for each object independently, not for all at once, so there is a for loop
2. Start on the very top and go down the tree. This is the reason why we have topologically sorted df in the previous step
3. For each object lookup all sources in df_arrows (get all rows from df_arrows where the object is the target). 
4. Each source -> target arrow has a logic expression and the entire 'relevant' of the target is just the logic expressions of 
    all incoming arrows, combined with a OR. 
5. A particular attention must be paid when a source is a 'note'. For those sources the 'expression' is 
    empty. 
    That is because there is no decision taken for those objects. A note is just an info to the user and forward to the 
    next field. There is also only one arrow coming out from a note. In this case we must use the relevant of 
    the 'note' and 'calculate' source itself as the expression of note -> target
    This would also be the case for 'calculate' objects, but their 'expression' has been populated already.  
    If we do not do that, then the target would pop up independently of the 'note/calculate' condition. That would be wrong. 
    Therefore, in df_source, the 'expression' for 'note' and 'calculate' is the 'relevant' of those sources. 
    To get those into df_sources, we merge it with df accordingly. 
    Therefore it is also important to do the logic from top to bottom, to assure that the relevant of the previous objects 
    has already been done. 
6. Another particular interest is for rhombus (previously entered data). Here we also need the relevant of the rhombus 
    itself, because it must be combined with the expresion by an AND. The rhombus itself is not seen to the user, 
    so the logic depends on his relevant. For the terms to be executed in the right order, the 'relevant' must be put 
    into brackets first. 
7. After those steps we have a df_sources dataframe where the 'expression' is correct for each of the arrows (each row). 
    As said in (4) they are combined with OR and written into the 'relevant' of the object we are looking at. 
8. Another major problem are pages that contain ONLY notes. As objects inside a page automatically inherit the relevant 
    of the page itself, their expression is entirely empty. The exit not then points to a target outside the page and 
    has no expression at all. The following object would then always be displayed 
    (or never, if there are other arrows pointing to)
    To deal with this we identify all those objects (groups that contain only notes and )
9. Another problem is when the first object in a page is a rhombus. It also gets no relevant generated. As a consequence, 
    we would get just the expression with 'and ()'
'''

df['relevant']=''

for elem in df.index:     
    # df_sources: dataframe that contains all connections pointing to the object 'elem'
    df_sources = df_arrows.loc[df_arrows['target']==elem,['source','source_type','expression']]
    # pulling the relevant of the sources into df_sources. This corresponds to the logic to each elem. 
    # 'xml-parent' is needed for rhombus at beginning of a page
    df_sources = df_sources.merge(df[['relevant','xml-parent']],how='left',left_on='source',right_index=True) 

    # when the source is a rhombus and it's relevant IS empty and the rhombus is on a page
    # you have to combine the expression with the relevant of the page
    # first merge with df again to the the relevant of the page
    df_sources = df_sources.merge(df[['relevant']],how='left',left_on='xml-parent',right_index=True,suffixes=('', '_page'))
    m=df_sources['source_type'].isin(['rhombus']) & (df_sources['relevant']=='') & df_sources['xml-parent'].isin(container_ids)
    df_sources.loc[m,'expression'] = df_sources.loc[m,'expression'] + ' and (' + df_sources.loc[m,'relevant_page'] + ')'    
    
    # when the source is a rhombus and it's relevant is NOT empty, you have to combine both with AND
    m=df_sources['source_type'].isin(['rhombus']) & (df_sources['relevant']!='')
    df_sources.loc[m,'expression'] = df_sources.loc[m,'expression'] + ' and (' + df_sources.loc[m,'relevant'] + ')'
    
    # when the source is a note, just take its relevant and put it into expression
    m=df_sources['source_type'].isin(['note'])
    df_sources.loc[m,'expression'] = df_sources.loc[m,'relevant']    

    # when the source is a note that is pointing out of a page that only contains 'notes' use the page relevant as 
    # its expression 
    m=df_sources['source'].isin(df_notes_outof_pure_notes_pages.index) # Mask to get pure note elements
    df_sources.loc[m,'expression'] = df_sources.loc[m,'relevant_page']
    #page_id = df.loc[df_sources.loc[m,'source'],'xml-parent'] # # get the page_ids of the pages the elments are in
    # df_sources.loc[m,'expression'] = df.loc[page_id,'relevant'].to_list()
    
    if df.loc[elem,'odk_type']!='count':
        df.loc[elem,'relevant'] = ' or '.join(filter(None,df_sources['expression']))
    else:
        # for counters the joining is number + number
        df.loc[elem,'relevant'] = ' + '.join(filter(None,df_sources['expression'])) 


# In[ ]:





# In[ ]:





# In[ ]:





# In[1118]:


# making summary
def make_summary(df):
    diagnose_colors=['f8cecc','ffe6cc','fff2cc','d5e8d4'] #red, orange, yellow, green
    df_diagnose=df.loc[(df['odk_type']=='calculate') & df['style'].str.contains('|'.join(diagnose_colors)),['value','name','relevant']]
    diagnose_index=df_diagnose.index
    df_diagnose['relevance']=df_diagnose['relevant']
    df_diagnose.loc[diagnose_index,'appearance']='center'
    df_diagnose['help::English (en)']=''
    df_diagnose['hint::English (en)']=''
    df_diagnose['constraint']=''
    df_diagnose['constraint message::English (en)']=''
    df_diagnose['required']=''
    df_diagnose['required message::English (en)']=''
    df_diagnose['calculation']=''
    df_diagnose['repeat_count']=''
    df_diagnose['media::image::English (en)']=''
    df_diagnose['type']='note'
    df_diagnose['value']='<p>' + df_diagnose['value'] + '</p>'
    df_diagnose['name']=df_diagnose['name'].replace({'d_':'label_'},regex=True)
    df_diagnose = df_diagnose[['type','name','value','help::English (en)','hint::English (en)','appearance','relevance','constraint','constraint message::English (en)','required','required message::English (en)','calculation','repeat_count','media::image::English (en)']]
    df_diagnose.rename(columns={'value':'label::English (en)'},inplace=True)
    
    intro = pd.read_excel('summary.xlsx').iloc[:4]
    
    extro = pd.read_excel('summary.xlsx').iloc[-2:]
    
    danger_signs = df_choices.loc[df_choices['list_name'].str.contains('select_signs') & ~df_choices['name'].str.contains('none')].copy()
    danger_signs['relevance']='selected(${' + danger_signs['list_name'] + '},\'' + danger_signs['name'] + '\')'
    danger_signs['appearance']='li'
    danger_signs['help::English (en)']=''
    danger_signs['hint::English (en)']=''
    danger_signs['constraint']=''
    danger_signs['constraint message::English (en)']=''
    danger_signs['required']=''
    danger_signs['required message::English (en)']=''
    danger_signs['calculation']=''
    danger_signs['repeat_count']=''
    danger_signs['media::image::English (en)']=''
    danger_signs['type']='note'
    danger_signs['name']='label_' + danger_signs['name']
    danger_signs = danger_signs[['type','name','label::English (en)','help::English (en)','hint::English (en)','appearance','relevance','constraint','constraint message::English (en)','required','required message::English (en)','calculation','repeat_count','media::image::English (en)']]
    
    df_new = pd.concat([intro,df_diagnose,pd.read_excel('summary.xlsx').iloc[4:6],danger_signs,extro])
    
    return df_new


# In[1119]:


df_summary = make_summary(df)


# In[ ]:





# In[1120]:


# resort the graph so that pages are grouped together

# ids of objects are page_headers pages
page_ids = df.loc[df['odk_type']=='container_page'].index

# new dataframe that contains only objects that are INSIDE pages (all pages combined)
df_pageObjects = df.loc[df['xml-parent'].isin(page_ids)]


# In[1121]:


'''
The topological sorting does not yet take into account pages (page-containers). Objects that are on the same page, must be 
grouped in order to wrap them up in begin_group ... end_group in odk. The topological_sort does not know what. 
Therefore we take out the objects that lie on pages from df and change the connectors in this manner: 
1. Connectors that leave out the page (exit-connectors) are replaced by connectors between the page head and the same targets. 
2. Connectors that are entirely inside the page are deleted
3. The connector between the page head and the first question inside the page is deleted as well
Then we do again a topological_sort of the entire graph. 
After that we make a topological graph for each page and than reinclude this page into the big graph (df)
'''

# resort the graph so that pages are grouped together

# ids of objects are page_headers pages
page_ids = df.loc[df['odk_type']=='container_page'].index

# new dataframe that contains only objects that are INSIDE pages (all pages combined)
df_pageObjects = df.loc[df['xml-parent'].isin(page_ids)]

# drop objects that are INSIDE pages from the main dataframe df
df.drop(df_pageObjects.index,inplace=True)

# Connectors:
# new df_arrows for objects on pages that point INSIDE the page, for topologically sorting each page
df_arrows_in_pages = df_arrows.loc[df_arrows['source'].isin(df_pageObjects.index) &                                     df_arrows['target'].isin(df_pageObjects.index)]

# new df_arrows for objects on pages that point outside of the page (exit connectors). 
# Needed to replace connectors in main df_arrows
df_arrows_out_pages = df_arrows.loc[df_arrows['source'].isin(df_pageObjects.index) &                                     ~df_arrows['target'].isin(df_pageObjects.index)]

# replace connectors from df_arrows_out_pages in df_arrows by connectors from the page_head to the same targets
df_arrows.loc[df_arrows_out_pages.index,'source'] = df_arrows.loc[df_arrows_out_pages.index,'container_id']

# in df_arrows, drop the connectors between objects that belong to pages (INSIDE connectors)
df_arrows.drop(df_arrows_in_pages.index,inplace=True)

# in df_arrows, also drop the connectors which point from the page-root to the first object INSIDE the page
# reset index, because you have manually added page_connectors on top that have messed it up!
df_arrows.reset_index(inplace=True)
df_arrows.drop(columns=['index'],inplace=True)
df_arrows.drop(df_arrows.loc[df_arrows['source_type']=='page'].index,inplace=True)


# In[1122]:


# make a new topological sort in the df without objects INSIDE pages, but page heads (begin_group) only: 

# make a directed graph 
dg = nx.from_pandas_edgelist(df_arrows, source='source', target='target', create_using=nx.DiGraph)
order = list(nx.lexicographical_topological_sort(dg))

# change order of rows
df=df.reindex(order)


# In[1123]:


# topologically sort each page and insert back into main dataframe df

# group df_page_Objects by page
gk = df_pageObjects.groupby('xml-parent')

# sort each page and put it into main dataframe df
for page, df_page in gk:
    df_arrows_in_page = df_arrows_in_pages.loc[df_arrows_in_pages['source'].isin(df_page.index)]
    
    # make a dag for the page
    dag = nx.from_pandas_edgelist(df_arrows_in_page, source='source', target='target', create_using=nx.DiGraph)
    order = list(nx.lexicographical_topological_sort(dag))
    
    # sort the page
    df_page=df_page.reindex(order)
    
    # get split row
    page_id = df_page['xml-parent'][0]
    
    # and 'end_group' row to its end
    df_page = df_page.append(pd.DataFrame([['UserObject','','','',page_id,'','','','end group','','','','','','','','','','','']],                            columns=df_page.columns))
    
    # put it back in main dataframe df
    # get split row
    page_id = df_page['xml-parent'][0]
    
    # split df
    df_top = df.loc[:page_id]
    df_bottom = df.loc[page_id:].drop(index=page_id)
    
    # concat 
    df = pd.concat([df_top,df_page,df_bottom])


# In[1124]:


# taking out rhombus objects of the graph

def cut_node(arr, key):
    d = {}
    for a, b in arr:
        d.setdefault(a, []).append(b)
    
    if d.get(key) is None:
        return arr
    
    ans = []
    fill_vals = d[key]
    for a, b in arr:
        if a != key:
            if b != key:
                ans.append((a, b))
            else:
                for val in fill_vals:
                    ans.append((a, val))
                    
    return ans

#data = [("u", "w"), ("v", "w"), ("w", "x"), ("w", "y")]    
#foo(data, "w")
# [('u', 'x'), ('u', 'y'), ('v', 'x'), ('v', 'y')]

rhombus_id = df.loc[df['odk_type']=='rhombus'].index
new_edges=list(dg.edges)

for node in rhombus_id: 
    new_edges = cut_node(new_edges,node)
    
dg = nx.from_edgelist(new_edges, create_using=nx.DiGraph)


# In[1125]:


# short term workaround for select_xxx + NAME to add the same name as list_name
m = df['odk_type'].isin(['select_one','select_multiple'])
df.loc[m,'odk_type'] = df.loc[m,'odk_type'] + ' ' + df.loc[m,'name']

# making df look like the 'survey' tab in an xls form
df[['repeat_count','appearance','required','required message::English (en)','calculation']]=''
df=df[['odk_type','name','value','help::English (en)','hint::English (en)','appearance','relevant','constraint',        'constraint_message','required','required message::English (en)','calculation','repeat_count','media::image::English (en)']]
df.rename(columns={'odk_type':'type','value':'label::English (en)','relevant':'relevance','constraint_message':'constraint message::English (en)'},inplace=True)

# rename begin group
df.replace({'container_page':'begin group'}, inplace=True)
# add 'field-list'
df.loc[df['type']=='begin group','appearance']='field-list'

# keep the ids of the rhombus and drop the rhombus objects from df
# drop rhombus
df.drop(df.loc[df['type']=='rhombus'].index,inplace=True)

# in 'calculate' fields move 'relevance' to calculate
df.loc[df['type']=='calculate','calculation'] = df.loc[df['type']=='calculate','relevance']
# add 'number() to fit with odk '
df.loc[df['type']=='calculate','calculation'] = 'number(' + df.loc[df['type']=='calculate','calculation'] + ')'
# delete entry in relevance column of 'calcuate' rows
df.loc[df['type']=='calculate','relevance'] = ''


# In[1126]:


# making df_choices look like the 'choices' tab in an xls form
df_choices.drop(columns=['odk_type'],inplace=True)


# In[1127]:


# make a 'settings' tab
now = datetime.now()
version=now.strftime('%Y%m%d%H%M')
indx=[[1]]

settings={'form_title':'MSF - pediatric','form_id':form_id,'version':version,'default_language':'English (en)','style':'pages'}
df_settings=pd.DataFrame(settings,index=indx)
df_settings.head()


# ## make standalone (for diagnostic AND treatment)

# In[1128]:


# adding top questions and populating the 'calculate' column of the calculate fields in order to make the treatment flow 
# STANDALONE

# making the top questions 

if treatment_flow == False:
    # for the diagnostic flow as a shortterm we extract all the 'calculates' where the name starts with 'load_'
    # this is because, at this stage we no longer can distinguish the data-load-calculates from the normal calcualtes
    # drawback is that now all data-loaders must have a name starting with 'load_'. In the future this will be fixed, probably 
    # by adding a new data_attribute 'load_data' and make a special data_loader object
    tt_input_options = df.loc[(df['type']=='calculate') & df['name'].str.contains('load_',na=False),['type','name','label::English (en)']]
else:        
    # for the treatment flow in Somalia (in the tt flow, the only calculate objects are from data load. For the diagnistic
    # this would not work)
    tt_input_options = df.loc[df['type']=='calculate',['type','name','label::English (en)']] # options of the select_multiple


tt_input_options.rename(columns={'type':'list_name'},inplace=True)
df_choices = pd.concat([df_choices,tt_input_options]) # concat the new options to df_choices

# make the first question for data load
if treatment_flow==True:
    data_load = ['select_multiple calculate','data_load','Choose diseases and conditions','','','','','','','','','','','']
else:
    data_load = ['select_multiple calculate','data_load','Define adaptable parameters','','','','','','','','','','','']

data_load = pd.DataFrame([data_load],columns=df.columns)
df = pd.concat([data_load,df])

# populate the load_ calculate fields
df.loc[(df['type']=='calculate') & df['name'].str.contains('load_',na=False),'calculation']='number(selected(${data_load}, \''+ df.loc[df['type']=='calculate','name'] + '\'))'


# In[1129]:


# populate constraint message to all select_multiple
df.loc[df['type'].str.contains('select_multiple',na=False),'constraint']='.=\'opt_none\' or not(selected(.,\'opt_none\'))'
df.loc[df['type'].str.contains('select_multiple',na=False),'constraint message::English (en)']='**None** cannot be selected together with symptoms.'


# In[1130]:


# load z-score into the df

# first drop the row containing calculate - load_zscore
df.drop(df.loc[df['name']=='load_z_score'].index,inplace=True)
df.drop(df.loc[df['name']=='load_z_score_wa'].index,inplace=True)
df_choices.drop(df_choices.loc[df_choices['name']=='load_z_score'].index,inplace=True) # remove the option 'zscore' from the data_loader
df_choices.drop(df_choices.loc[df_choices['name']=='load_z_score_wa'].index,inplace=True) # remove the option 'zscore_wa' from the data_loader
dfz=pd.read_excel('z_score_xlsForm.xlsx')
dfz.fillna('',inplace=True)
df=pd.concat([dfz,df])


# In[1131]:


# concat summary to df
df = pd.concat([df,df_summary])


# In[ ]:





# In[ ]:





# In[1132]:


# add the 'quick' appearance to all select_one
df.loc[df['type'].str.contains('select_one',na=False),'appearance']='quick'

# drop the load field
df.drop({df.loc[df['label::English (en)']=='Load Data'].index[0]},inplace=True)


# In[1133]:


'''
From CHT Docs

Countdown Timer: A visual timer widget that starts when tapped/clicked, and has an audible alert when done. 
To use it create a note field with an appearance set to countdown-timer. 
The duration of the timer is the field’s value, which can be set in the XLSForm’s default column. 
If this value is not set, the timer will be set to 60 seconds.

Currently not implemented in TRICC, but hard coded here
'''
df.loc[df['label::English (en)'].str.contains('START',na=False),'appearance']='countdown-timer'


# In[1134]:


# make the xlsx file! 
 
#create a Pandas Excel writer using XlsxWriter as the engine
writer = pd.ExcelWriter(output_file, engine='xlsxwriter')


df.to_excel(writer, sheet_name='survey',index=False)
df_choices.to_excel(writer, sheet_name='choices',index=False)
df_settings.to_excel(writer, sheet_name='settings',index=False)

#close the Pandas Excel writer and output the Excel file
writer.save()

# run this on a windows python instance because if not then the generated xlsx file remains open
writer.close()
writer.handles = None


# In[1135]:


# converting into xls-form
from pyxform import xls2xform

import shutil

# When passing input-file as a string into the command, it fails. Only works hardcoded, don kno why. 
# solution: copy file here
# shutil.copy(source_path, './msfecare-ped.xlsx')


#%%cmd
#powershell xls2xform _1_data.xlsx

# command to execute shell script in python console (for linux environment)
#%run -i /home/rafael/anaconda3/lib/python3.8/site-packages/pyxform/xls2xform.py _1_data.xlsx _1_data.xml
#%run -i /home/rafael/anaconda3/lib/python3.8/site-packages/pyxform/xls2xform.py _2_data.xlsx _2_data.xml

# command to execute shell script in python console (for win environment)
# %run -i c:\users\kluera\anaconda3\lib\site-packages\pyxform\xls2xform.py msfecare-ped.xlsx msfecare-ped.xml
# %run -i c:\users\kluera\anaconda3\lib\site-packages\pyxform\xls2xform.py diagnose1.xlsx msfecare-ped.xml
get_ipython().run_line_magic('run', '-i c:\\users\\kluera\\anaconda3\\lib\\site-packages\\pyxform\\xls2xform.py msfecare_ped.xlsx msfecare_ped.xml')


# In[ ]:


df.to_csv('output.csv')

