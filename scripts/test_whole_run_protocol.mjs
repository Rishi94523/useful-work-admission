import assert from 'node:assert/strict';
import {record,commit,audit,sample,passProbability} from '../research/whole_run_protocol.mjs';
const units=[{seed:1},{seed:2}],runs=units.map(u=>({ok:true,score:-5,pose:'fixed-best-pose',trace:[u.seed,100,2*u.seed,200]})),records=runs.map(record);
const c=await commit('lease',units,records);
assert((await audit('lease',units,c,[0,1],records,u=>runs[u.seed-1])).accepted);
// Same final minimum and plausible early prefix must not impersonate full run.
const short=records.map(r=>({...r,trace:r.trace.slice(0,2)})),forged=await commit('lease',units,short);
assert(!(await audit('lease',units,forged,[0],[short[0]],u=>runs[u.seed-1])).accepted);
await assert.rejects(audit('other',units,c,[0],[records[0]],u=>runs[u.seed-1]));
await assert.rejects(audit('lease',units,c,[0,0],records,u=>runs[u.seed-1]));
assert(!(await audit('lease',units,c,[1],[records[0]],u=>runs[u.seed-1])).accepted);
assert.equal(passProbability(2,4,2),1/6);assert.equal(passProbability(1,4,2),0);
for(let i=0;i<100;i++)assert.equal(new Set(sample(16,8)).size,8);
console.log('Whole-run protocol security regressions passed');
