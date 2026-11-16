"""Freeze one candidate against existing originals, without provider dispatch."""
import json,hashlib
from pathlib import Path
from .compound import project
from backend.services.structured_extraction import request_schema
from jsonschema import Draft202012Validator


def prepare(source,output):
 output.mkdir(exist_ok=False,parents=True);rows=[]
 for path in sorted(source.glob('*.json')):
  case=json.loads(path.read_text())
  if 'messages' not in case:continue
  before=case['messages']['T'];after=project(before)
  Draft202012Validator.check_schema(request_schema(after))
  case['messages']['compound259']=after;case['profiles']['compound259']='deepseek-flash'
  target=output/path.name;target.write_text(json.dumps(case,ensure_ascii=False,indent=2))
  def sizes(messages):
   return {m['content'].split('\n',1)[0] if i else 'rules':len(m['content']) for i,m in enumerate(messages)}
  rows.append({'case':case['name'],'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'before_chars':sizes(before),'after_chars':sizes(after)})
 (output/'manifest.json').write_text(json.dumps({'paid_calls':0,'rows':rows},ensure_ascii=False,indent=2))
 return rows
