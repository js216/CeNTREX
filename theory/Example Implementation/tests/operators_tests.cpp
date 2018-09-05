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
   State<DecoupledBasis> S000000 {s000000, 3.14};
   State<DecoupledBasis> S000001 {s000001, 3.14};
   State<DecoupledBasis> S000010 {s000010, 3.14};
   State<DecoupledBasis> S000100 {s000100, 3.14};
   State<DecoupledBasis> S001000 {s001000, 3.14};
   State<DecoupledBasis> S010000 {s010000, 3.14};
   State<DecoupledBasis> S100000 {s100000, 3.14};
   State<DecoupledBasis> S120000 {s120000, 2.71};

   // test J2
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
}
