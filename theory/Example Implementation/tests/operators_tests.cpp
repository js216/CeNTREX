#include <iostream>
#include <limits>
#include "../operators/DecoupledBasisOperators.h"

const double epsilon = 10 * std::numeric_limits<double>::epsilon();

int main()
{
   // create basis states
   DecoupledBasis s000000 {0,0,0,0,0,0};
   DecoupledBasis s000001 {0,0,0,0,0,1};
   DecoupledBasis s000010 {0,0,0,0,1,0};
   DecoupledBasis s000100 {0,0,0,1,0,0};
   DecoupledBasis s001000 {0,0,1,0,0,0};
   DecoupledBasis s010000 {0,1,0,0,0,0};
   DecoupledBasis s100000 {1,0,0,0,0,0};
   DecoupledBasis s120000 {1,2,0,0,0,0};

   // create superposition States
   State<DecoupledBasis> S000000 {s000000, 1.0};
   State<DecoupledBasis> S000001 {s000001, 1.0};
   State<DecoupledBasis> S000010 {s000010, 1.0};
   State<DecoupledBasis> S000100 {s000100, 1.0};
   State<DecoupledBasis> S001000 {s001000, 1.0};
   State<DecoupledBasis> S010000 {s010000, 1.0};
   State<DecoupledBasis> S100000 {s100000, 1.0};
   State<DecoupledBasis> S120000 {s120000, 1.0};

   // test J2 using BasisState as input
   if (J2(s000000) * s000000 != 0.0) return 1;
   if (J2(s000000) * s000010 != 0.0) return 2;
   if (J2(s000000) * s000100 != 0.0) return 3;
   if (J2(s000000) * s001000 != 0.0) return 4;
   if (J2(s000000) * s010000 != 0.0) return 5;
   if (J2(s000000) * s100000 != 0.0) return 6;
   //
   if (J2(s000001) * s000000 != 0.0) return 7;
   if (J2(s000001) * s000010 != 0.0) return 8;
   if (J2(s000001) * s000100 != 0.0) return 9;
   if (J2(s000001) * s001000 != 0.0) return 10;
   if (J2(s000001) * s010000 != 0.0) return 11;
   if (J2(s000001) * s100000 != 0.0) return 12;
   //
   if (J2(s000010) * s000000 != 0.0) return 13;
   if (J2(s000010) * s000010 != 0.0) return 14;
   if (J2(s000010) * s000100 != 0.0) return 15;
   if (J2(s000010) * s001000 != 0.0) return 16;
   if (J2(s000010) * s010000 != 0.0) return 17;
   if (J2(s000010) * s100000 != 0.0) return 18;
   //
   if (J2(s000100) * s000000 != 0.0) return 19;
   if (J2(s000100) * s000010 != 0.0) return 20;
   if (J2(s000100) * s000100 != 0.0) return 21;
   if (J2(s000100) * s001000 != 0.0) return 22;
   if (J2(s000100) * s010000 != 0.0) return 23;
   if (J2(s000100) * s100000 != 0.0) return 24;
   //
   if (J2(s001000) * s000000 != 0.0) return 25;
   if (J2(s001000) * s000010 != 0.0) return 26;
   if (J2(s001000) * s000100 != 0.0) return 27;
   if (J2(s001000) * s001000 != 0.0) return 28;
   if (J2(s001000) * s010000 != 0.0) return 29;
   if (J2(s001000) * s100000 != 0.0) return 30;
   //
   if (J2(s010000) * s000000 != 0.0) return 31;
   if (J2(s010000) * s000010 != 0.0) return 32;
   if (J2(s010000) * s000100 != 0.0) return 33;
   if (J2(s010000) * s001000 != 0.0) return 34;
   if (J2(s010000) * s010000 != 0.0) return 35;
   if (J2(s010000) * s100000 != 0.0) return 36;
   //
   if (J2(s100000) * s000000 != 0.0) return 37;
   if (J2(s100000) * s000010 != 0.0) return 38;
   if (J2(s100000) * s000100 != 0.0) return 39;
   if (J2(s100000) * s001000 != 0.0) return 40;
   if (J2(s100000) * s010000 != 0.0) return 41;
   if (J2(s100000) * s100000 != 2.0) return 42;

   // test J2 using State input
   if (J2(S000000) * s000000 != 0.0) return 111;
   if (J2(S000000) * s000010 != 0.0) return 112;
   if (J2(S000000) * s000100 != 0.0) return 113;
   if (J2(S000000) * s001000 != 0.0) return 114;
   if (J2(S000000) * s010000 != 0.0) return 115;
   if (J2(S000000) * s100000 != 0.0) return 116;
   //
   if (J2(S000001) * s000000 != 0.0) return 117;
   if (J2(S000001) * s000010 != 0.0) return 118;
   if (J2(S000001) * s000100 != 0.0) return 119;
   if (J2(S000001) * s001000 != 0.0) return 1110;
   if (J2(S000001) * s010000 != 0.0) return 1111;
   if (J2(S000001) * s100000 != 0.0) return 1112;
   //
   if (J2(S000010) * s000000 != 0.0) return 1113;
   if (J2(S000010) * s000010 != 0.0) return 1114;
   if (J2(S000010) * s000100 != 0.0) return 1115;
   if (J2(S000010) * s001000 != 0.0) return 1116;
   if (J2(S000010) * s010000 != 0.0) return 1117;
   if (J2(S000010) * s100000 != 0.0) return 1118;
   //
   if (J2(S000100) * s000000 != 0.0) return 1119;
   if (J2(S000100) * s000010 != 0.0) return 1120;
   if (J2(S000100) * s000100 != 0.0) return 1121;
   if (J2(S000100) * s001000 != 0.0) return 1122;
   if (J2(S000100) * s010000 != 0.0) return 1123;
   if (J2(S000100) * s100000 != 0.0) return 1124;
   //
   if (J2(S001000) * s000000 != 0.0) return 1125;
   if (J2(S001000) * s000010 != 0.0) return 1126;
   if (J2(S001000) * s000100 != 0.0) return 1127;
   if (J2(S001000) * s001000 != 0.0) return 1128;
   if (J2(S001000) * s010000 != 0.0) return 1129;
   if (J2(S001000) * s100000 != 0.0) return 1130;
   //
   if (J2(S010000) * s000000 != 0.0) return 1131;
   if (J2(S010000) * s000010 != 0.0) return 1132;
   if (J2(S010000) * s000100 != 0.0) return 1133;
   if (J2(S010000) * s001000 != 0.0) return 1134;
   if (J2(S010000) * s010000 != 0.0) return 1135;
   if (J2(S010000) * s100000 != 0.0) return 1136;
   //
   if (J2(S100000) * s000000 != 0.0) return 1137;
   if (J2(S100000) * s000010 != 0.0) return 1138;
   if (J2(S100000) * s000100 != 0.0) return 1139;
   if (J2(S100000) * s001000 != 0.0) return 1140;
   if (J2(S100000) * s010000 != 0.0) return 1141;
   if (J2(S100000) * s100000 != 2.0) return 1142;
}
