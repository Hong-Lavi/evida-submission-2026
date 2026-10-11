Minimize
Obj: 0.4 aD1 + 0.2 nU1 + 0.2 nD1 + 0.2 nU2 + 0.2 nD2
Subject To
m1: n2 - aD1 <= 1
m2: n2 + aD1 >= 1
s1: nU1 - nD1 + nAc1 - n1 = 0
a1: nAc1 = 0
u1: nU1 + nD1 <= 1
s2: nU2 - nD2 + nAc2 - n2 = 0
a2: nAc2 = 0
u2: nU2 + nD2 <= 1
eu: eU1 - nU1 = 0
ed: eD1 - nD1 = 0
t: n2 - eU1 + eD1 = 0
d: nDs2 - nDs1 >= 1
Bounds
-1 <= n1 <= 1
0 <= nU1 <= 1
0 <= nD1 <= 1
-1 <= nAc1 <= 1
0 <= nDs1 <= 3
-1 <= n2 <= 1
0 <= nU2 <= 1
0 <= nD2 <= 1
-1 <= nAc2 <= 1
0 <= nDs2 <= 3
0 <= eU1 <= 1
0 <= eD1 <= 1
0 <= aD1 <= 2
Binaries
nU1
nD1
nU2
nD2
eU1
eD1
Generals
n1
nAc1
n2
nAc2
aD1
End
