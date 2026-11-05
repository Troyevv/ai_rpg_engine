import {defaultCreation,type Creation} from '../WorldCreationSettings';
export type IdeaBuffer={text:string;name:string;useIdea:boolean;creation:Creation};
const key=(id:string)=>'workshop-idea-form:'+id;
export function readIdeaBuffer(id:string):IdeaBuffer|null {
  try {const v=JSON.parse(sessionStorage.getItem(key(id))||'null');
    return v&&typeof v.text==='string'&&typeof v.name==='string'&&v.creation?{...v,creation:{...structuredClone(defaultCreation),...v.creation}}:null;
  } catch {return null}
}
export function writeIdeaBuffer(id:string,value:IdeaBuffer):boolean {
  try {sessionStorage.setItem(key(id),JSON.stringify(value));return true} catch {return false}
}
