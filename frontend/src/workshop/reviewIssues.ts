export type ReviewIssue = {message:string;severity?:string;path?:string|null;patch_paths?:string[];related_paths?:string[]};
export type ReviewRow = {message:string;severity:'error'|'warning'|'recommendation';paths:string[];sources:string[]};
const priority={error:0,warning:1,recommendation:2};

/** Merge display duplicates without losing stronger severity or addressed objects. */
export function reviewIssues(review:ReviewIssue[]=[],validation:{errors?:string[];warnings?:string[];diagnostics?:ReviewIssue[]}={},imports:string[]=[]):ReviewRow[]{
 const rows=new Map<string,ReviewRow>();
 const add=(message:string,severity:ReviewRow['severity'],paths:(string|null|undefined)[],source:string)=>{
  const clean=message.trim();if(!clean)return;
  const row=rows.get(clean)||{message:clean,severity,paths:[],sources:[]};
  if(priority[severity]<priority[row.severity])row.severity=severity;
  row.paths=[...new Set([...row.paths,...paths.filter((p):p is string=>!!p)])];
  row.sources=[...new Set([...row.sources,source])];rows.set(clean,row);
 };
 for(const issue of review)add(issue.message,issue.severity==='blocker'?'error':issue.severity==='recommendation'?'recommendation':'warning',[issue.path,...issue.patch_paths||[],...issue.related_paths||[]],'Смысловая проверка');
 for(const issue of validation.diagnostics||[])add(issue.message,issue.severity==='recommendation'?'recommendation':issue.severity==='warning'?'warning':'error',[issue.path],'Структура мира');
 const addText=(text:string,severity:ReviewRow['severity'],source:string)=>{
  // Validation also serializes addressed diagnostics as “/path: message”.
  const addressed=/^(\/[^\n]*?):\s+([\s\S]+)$/.exec(text);
  add(addressed?.[2]||text,severity,addressed?[addressed[1]]:[],source);
 };
 for(const text of validation.errors||[])addText(text,'error','Структура мира');
 for(const text of validation.warnings||[])addText(text,'warning','Проверка данных');
 for(const text of imports)addText(text,'warning','Импорт');
 return [...rows.values()].sort((a,b)=>priority[a.severity]-priority[b.severity]);
}
