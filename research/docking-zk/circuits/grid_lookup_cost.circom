pragma circom 2.2.3;
include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
// Cost probe for ONE authenticated table lookup, not a scientific workload.
// Table leaves bind index and a 32-bit offset encoding of signed grid values.
template Lookup(D) {
signal input root;signal input index;signal input value;signal input siblings[D];
component address=Num2Bits(D);address.in <== index;
component bounded=Num2Bits(32);bounded.in <== value;
component leaf=Poseidon(2);leaf.inputs[0] <== index;leaf.inputs[1] <== value;
signal hash[D+1];hash[0] <== leaf.out;
signal left[D];signal right[D];component node[D];
for(var i=0;i<D;i++) {
left[i] <== hash[i]+address.out[i]*(siblings[i]-hash[i]);
right[i] <== siblings[i]+address.out[i]*(hash[i]-siblings[i]);
node[i]=Poseidon(2);node[i].inputs[0] <== left[i];node[i].inputs[1] <== right[i];hash[i+1] <== node[i].out;
}
hash[D] === root;
}
component main {public [root]} = Lookup(20);
