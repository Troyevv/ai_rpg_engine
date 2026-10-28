import type {Job} from './types';
// One projection of actual job/SSE state. No clocks or invented progress.
export function callActivity(job?:Job|null,reconnecting=false) {
 if(!job||job.status==='saved')return 'connected';
 if(job.status==='error')return job.narrative_complete?'callApplyFailed':'reactionFailed';
 if(job.status==='stopped')return 'callStopped';
 if(reconnecting)return 'callReconnecting';
 if(job.narrative_complete||['extracting','validating','committing'].includes(job.status))return 'callApplying';
 return job.narrative.trim()?'callStreaming':'callWaiting';
}
export function canStopCall(job?:Job|null) {
 return !!job&&['queued','generating','extracting'].includes(job.status);
}
