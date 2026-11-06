import {describe,it,expect} from 'vitest';
import {callActivity,canStopCall} from '../src/callActivity';
import type {Job} from '../src/types';
const job=(status:string,narrative='',narrative_complete=false)=>({status,narrative,narrative_complete}) as Job;
describe('actual call lifecycle',()=>{
 it('waits for real tokens, then hands off to speech and consequences',()=>{
  expect(callActivity(null)).toBe('connected');
  expect(callActivity(job('generating'))).toBe('callWaiting');
  expect(callActivity(job('generating','  '))).toBe('callWaiting');
  expect(callActivity(job('generating','Да'))).toBe('callStreaming');
  expect(callActivity(job('generating','Да',true))).toBe('callApplying');
  for(const status of ['extracting','validating','committing'])expect(callActivity(job(status))).toBe('callApplying');
  expect(callActivity(job('saved'))).toBe('connected');
 });
 it('prioritizes terminal states over SSE reconnect and exposes safe stop',()=>{
  expect(callActivity(job('generating'),true)).toBe('callReconnecting');
  expect(callActivity(job('error','Ответ',true))).toBe('callApplyFailed');
  expect(callActivity(job('error'),true)).toBe('reactionFailed');
  expect(callActivity(job('stopped'),true)).toBe('callStopped');
  for(const status of ['queued','generating','extracting'])expect(canStopCall(job(status))).toBe(true);
  for(const status of ['validating','saved','error','stopped'])expect(canStopCall(job(status))).toBe(false);
 });
});
