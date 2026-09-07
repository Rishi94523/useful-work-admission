pragma circom 2.2.3;
include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

// CALIBRATION ONLY: reduced 8-atom ligand / 8-atom receptor contact potential.
// This is not Vina's force field, flexible docking, or a binding prediction.
template ContactPair() {
    signal input a[3]; signal input b[3];
    signal output energy;
    signal delta[3]; signal square[3]; signal d2;
    for (var k=0;k<3;k++) { delta[k] <== a[k]-b[k]; square[k] <== delta[k]*delta[k]; }
    d2 <== square[0]+square[1]+square[2];
    component bounded = Num2Bits(26); bounded.in <== d2;
    component clash = LessThan(27); clash.in[0] <== d2; clash.in[1] <== 900;
    component contact = LessThan(27); contact.in[0] <== d2; contact.in[1] <== 2500;
    signal repulsion; signal attraction;
    repulsion <== clash.out*(900-d2);
    attraction <== contact.out*(2500-d2);
    energy <== 10*repulsion-attraction;
}

template ContactSearch(N) {
    signal input seed;
    signal input ligand[8][3]; signal input receptor[8][3];
    signal output bestScore; signal output bestIndex;
    component ligandBounds[8][3]; component receptorBounds[8][3];
    for(var a=0;a<8;a++) for(var k=0;k<3;k++) {
        ligandBounds[a][k]=Num2Bits(12); ligandBounds[a][k].in <== ligand[a][k];
        receptorBounds[a][k]=Num2Bits(12); receptorBounds[a][k].in <== receptor[a][k];
    }
    component prf[N]; component bits[N];
    signal shift[N][3]; signal pose[N][8][3];
    component pair[N][8][8]; signal score[N]; component scoreBounds[N];
    signal best[N+1]; signal index[N+1]; component better[N];
    best[0] <== 1048575; index[0] <== 0;
    for(var i=0;i<N;i++) {
        prf[i]=Poseidon(2); prf[i].inputs[0] <== seed; prf[i].inputs[1] <== i;
        // Strict field decomposition avoids alternate bit representations.
        bits[i]=Num2Bits_strict(); bits[i].in <== prf[i].out;
        for(var k=0;k<3;k++) {
            var offset=0;
            for(var bit=0;bit<6;bit++) offset += bits[i].out[k*6+bit]*(2**bit);
            shift[i][k] <== 3*offset-94;
            for(var a=0;a<8;a++) pose[i][a][k] <== ligand[a][k]+shift[i][k];
        }
        var total=160000;
        for(var a=0;a<8;a++) for(var b=0;b<8;b++) {
            pair[i][a][b]=ContactPair();
            for(var k=0;k<3;k++) { pair[i][a][b].a[k] <== pose[i][a][k]; pair[i][a][b].b[k] <== receptor[b][k]; }
            total += pair[i][a][b].energy;
        }
        score[i] <== total;
        scoreBounds[i]=Num2Bits(20); scoreBounds[i].in <== score[i];
        better[i]=LessThan(21); better[i].in[0] <== score[i]; better[i].in[1] <== best[i];
        best[i+1] <== best[i]+better[i].out*(score[i]-best[i]);
        index[i+1] <== index[i]+better[i].out*(i-index[i]);
    }
    bestScore <== best[N]; bestIndex <== index[N];
}
