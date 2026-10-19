import test from 'node:test';
import assert from 'node:assert/strict';
import {jobActive,transferLabel,watchJob} from '../web/addon_jobs.mjs';

test('polling follows queued/running work and delivers a terminal result exactly once',async()=>{
  const snapshots=[{status:'queued'},{status:'running',cancel_requested:true},{status:'cancelled'}],seen=[],finished=[];
  await watchJob({getJob:async()=>snapshots.shift(),isCurrent:()=>true,onUpdate:job=>seen.push(job.status),onFinish:job=>finished.push(job.status),delay:async()=>{}});
  assert.deepEqual(seen,['queued','running','cancelled']);
  assert.deepEqual(finished,['cancelled']);
  assert.equal(jobActive({status:'running',cancel_requested:true}),true);
  assert.equal(jobActive({status:'interrupted'}),false);
});

test('a delayed job response never updates a page after navigation',async()=>{
  let current=true,complete;const effects=[];
  const pending=watchJob({getJob:()=>new Promise(resolve=>{complete=resolve;}),isCurrent:()=>current,onUpdate:()=>effects.push('updated'),onFinish:()=>effects.push('finished')});
  current=false;complete({status:'succeeded',result:{review:{id:'late'}}});
  await pending;assert.deepEqual(effects,[]);
});

test('navigation during a polling interval prevents another request',async()=>{
  let current=true,calls=0;
  await watchJob({getJob:async()=>{calls++;return {status:'running'};},isCurrent:()=>current,onUpdate:()=>{},onFinish:()=>assert.fail('Still running'),delay:async()=>{current=false;}});
  assert.equal(calls,1);
});

test('status failures are exposed for reconnect guidance and do not run completion actions',async()=>{
  await assert.rejects(watchJob({getJob:async()=>{throw Error('Disconnected');},isCurrent:()=>true,onUpdate:()=>assert.fail(),onFinish:()=>assert.fail()}),/Disconnected/);
});

test('transfer labels report actual byte counts without inventing a total',()=>{
  assert.equal(transferLabel({progress:{received_bytes:2048,total_bytes:null}}),'2.0 KiB received');
  assert.equal(transferLabel({progress:{received_bytes:2048,total_bytes:4096}}),'2.0 KiB received / 4.0 KiB');
  assert.equal(transferLabel({progress:{received_bytes:0,total_bytes:null}}),'');
});
