// Single-party DEVELOPMENT setup. Entropy is ephemeral, never stored in logs.
import {randomBytes} from 'node:crypto';
import * as snarkjs from 'snarkjs';
const [kind,source,target]=process.argv.slice(2);
const entropy=randomBytes(64).toString('hex');
if(kind==='ptau') await snarkjs.powersOfTau.contribute(source,target,'Local development contribution',entropy);
else if(kind==='zkey') await snarkjs.zKey.contribute(source,target,'Local development contribution',entropy);
else throw new Error('Unknown contribution kind');
console.log('Development contribution complete; use a reviewed ceremony for deployment.');
process.exit(0);
