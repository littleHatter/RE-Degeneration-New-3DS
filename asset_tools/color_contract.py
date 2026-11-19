"""Enforce vertex-color index bounds from the actual software model.
Only constant-color arrays may be extended. Nonconstant remapping is not guessed.
"""
import struct
from directory_codec import parse
from group_codec import iw_hash
from software_model_codec import read
from component_codec import Unsupported
class ColorContract:
 def __init__(self,environment):
  self.required={}
  for r,s,t in parse(environment).spans():
   if r.class_id!=iw_hash('CIwModel'):continue
   data=environment[s:t-8 if t==len(environment) else t];model=read(data)
   groups=[b for b in model['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups')]
   if len(groups)!=1:raise Unsupported('model color-index group count')
   g=groups[0];slot=g['roles'][2];stride=sum(v<128 for v in g['roles'])
   if slot>=128:self.required[r.name_hash]=0;continue
   if slot>=stride:raise ValueError('invalid color-index role')
   indices=struct.unpack('<'+str(len(g['indices'])//2)+'H',g['indices']);colors=indices[slot::stride]
   self.required[r.name_hash]=max(colors,default=-1)+1
 def ensure(self,component,stats):
  if 'colors' not in component:return
  model=component['model']
  if model not in self.required:raise Unsupported(f'unresolved color contract for model {model:08x}')
  colors=component['colors'];need=self.required[model];have=colors['count']
  if len(colors['colors'])!=have*4:raise ValueError('invalid color array length')
  stats['color_contracts_checked']+=1
  if have>=need:return
  values={colors['colors'][i:i+4] for i in range(0,have*4,4)}
  if len(values)!=1:raise Unsupported('nonconstant vertex colors require geometric remapping')
  colors['colors']=next(iter(values))*need;colors['count']=need
  stats['constant_color_extensions']+=1;stats['added_color_entries']+=need-have
  assert colors['count']>=need
