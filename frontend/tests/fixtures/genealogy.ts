import type {Genealogy,SocialRelation} from '../../src/types';
export const person=(id:string,name=id)=>({id,name,life_status:'alive'});
export const relation=(id:string,source_id:string,target_id:string,kind='parent'):SocialRelation=>({id,source_id,target_id,kind,certainty:'known',status:'active',outcome:''});
// Screenshot names and visible two-generation shape. Relation records below are
// explicit test inputs, not a recovered/exported user save (none was provided).
export const screenshotFamily:Genealogy={
 nodes:[person('marina','Марина Волкова'),person('sergey','Сергей Волков'),person('ilya','Илья Александров'),person('katya','Катя Волкова'),person('sonya','Соня Величкина'),person('timur','Тимур Волков')],
 edges:[relation('marriage','marina','sergey','spouse'),...['katya','sonya','timur'].flatMap(c=>['marina','sergey'].map(p=>relation(`${p}-${c}`,p,c))),relation('care','marina','ilya','guardian'),relation('sisters','katya','sonya','sibling'),relation('siblings','katya','timur','sibling')],
 kinship:[],truncated:false,
};
