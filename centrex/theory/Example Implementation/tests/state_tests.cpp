#include <iostream>
#include <complex>
#include <limits>
#include "../states/State.h"
#include "../states/BasisState.h"
#include "../bases/DecoupledBasis.h"

const double epsilon = 10 * std::numeric_limits<double>::epsilon();

int main()
{
   // create basis states
   DecoupledBasis s000000 {0.0,0,0,0,0,0};
   DecoupledBasis sm00000 {-0.0,0,0,0,0,0};
   DecoupledBasis s000001 {0,0,0,0,0,1};
   DecoupledBasis s000010 {0,0,0,0,1,0};
   DecoupledBasis s000100 {0,0,0,1,0,0};
   DecoupledBasis s001000 {0,0,1,0,0,0};
   DecoupledBasis s010000 {0,1,0,0,0,0};
   DecoupledBasis s100000 {1,0,0,0,0,0};

   // check comparisons
   if (s000000 != sm00000) std::cout << "error 111\n";
   if (s000000 == s000001) std::cout << "error 1\n";
   if (s000000 == s000010) std::cout << "error 2\n";
   if (s000000 == s000100) std::cout << "error 3\n";
   if (s000000 == s001000) std::cout << "error 4\n";
   if (s000000 == s010000) std::cout << "error 5\n";
   if (s000000 == s100000) std::cout << "error 6\n";
   if (s000001 != s000001) std::cout << "error 7\n";
   if (s000010 != s000010) std::cout << "error 8\n";
   if (s000100 != s000100) std::cout << "error 9\n";
   if (s001000 != s001000) std::cout << "error 10\n";
   if (s010000 != s010000) std::cout << "error 11\n";
   if (s100000 != s100000) std::cout << "error 12\n";

   // check inner products
   if (s000000 * s000000 != 1.0) std::cout << "error 13\n";
   if (s000001 * s000001 != 1.0) std::cout << "error 14\n";
   if (s000010 * s000010 != 1.0) std::cout << "error 15\n";
   if (s000100 * s000100 != 1.0) std::cout << "error 16\n";
   if (s001000 * s001000 != 1.0) std::cout << "error 17\n";
   if (s010000 * s010000 != 1.0) std::cout << "error 18\n";
   if (s100000 * s100000 != 1.0) std::cout << "error 19\n";
   if (s000000 * s000001 != 0.0) std::cout << "error 20\n";
   if (s000000 * s000010 != 0.0) std::cout << "error 21\n";
   if (s000000 * s000100 != 0.0) std::cout << "error 22\n";
   if (s000000 * s001000 != 0.0) std::cout << "error 23\n";
   if (s000000 * s010000 != 0.0) std::cout << "error 24\n";
   if (s000000 * s100000 != 0.0) std::cout << "error 25\n";

   // create superposition States
   State<DecoupledBasis> empty {};
   State<DecoupledBasis> a {s000000, 1.00};
   State<DecoupledBasis> S000000 {s000000, 3.14};
   State<DecoupledBasis> S000001 {s000001, 3.14};
   State<DecoupledBasis> S000010 {s000010, 3.14};
   State<DecoupledBasis> S000100 {s000100, 3.14};
   State<DecoupledBasis> S001000 {s001000, 3.14};
   State<DecoupledBasis> S010000 {s010000, 3.14};
   State<DecoupledBasis> S100000 {s100000, 3.14};

   // check comparisons
   if (S000000 == S000001) std::cout << "error 26\n";
   if (S000000 == S000010) std::cout << "error 27\n";
   if (S000000 == S000100) std::cout << "error 28\n";
   if (S000000 == S001000) std::cout << "error 29\n";
   if (S000000 == S010000) std::cout << "error 30\n";
   if (S000000 == S100000) std::cout << "error 31\n";
   if (S000001 != S000001) std::cout << "error 32\n";
   if (S000010 != S000010) std::cout << "error 33\n";
   if (S000100 != S000100) std::cout << "error 34\n";
   if (S001000 != S001000) std::cout << "error 35\n";
   if (S010000 != S010000) std::cout << "error 36\n";
   if (S100000 != S100000) std::cout << "error 37\n";

   // check inner products between States
   if (S000000 * S000000 != 9.8596) std::cout << "error 38\n";
   if (S000001 * S000001 != 9.8596) std::cout << "error 39\n";
   if (S000010 * S000010 != 9.8596) std::cout << "error 40\n";
   if (S000100 * S000100 != 9.8596) std::cout << "error 41\n";
   if (S001000 * S001000 != 9.8596) std::cout << "error 42\n";
   if (S010000 * S010000 != 9.8596) std::cout << "error 43\n";
   if (S100000 * S100000 != 9.8596) std::cout << "error 44\n";
   if (empty * empty != 0.0) std::cout << "error 45\n";
   if (empty * S000000 != 0.0) std::cout << "error 46\n";
   if (S000000 * S000001 != 0.0) std::cout << "error 47\n";
   if (S000000 * S000010 != 0.0) std::cout << "error 48\n";
   if (S000000 * S000100 != 0.0) std::cout << "error 49\n";
   if (S000000 * S001000 != 0.0) std::cout << "error 50\n";
   if (S000000 * S010000 != 0.0) std::cout << "error 51\n";
   if (S000000 * S100000 != 0.0) std::cout << "error 52\n";
   if (a * S000000 != 3.14) std::cout << "error 53\n";

   // check inner products between States and BasisStates
   if (s000000 * S000000 != 3.14) std::cout << "error 66\n";
   if (s000001 * S000001 != 3.14) std::cout << "error 67\n";
   if (s000010 * S000010 != 3.14) std::cout << "error 68\n";
   if (s000100 * S000100 != 3.14) std::cout << "error 69\n";
   if (s001000 * S001000 != 3.14) std::cout << "error 70\n";
   if (s010000 * S010000 != 3.14) std::cout << "error 71\n";
   if (s100000 * S100000 != 3.14) std::cout << "error 72\n";
   if (s000000 * S000001 != 0.0) std::cout << "error 73\n";
   if (s000000 * S000010 != 0.0) std::cout << "error 74\n";
   if (s000000 * S000100 != 0.0) std::cout << "error 75\n";
   if (s000000 * S001000 != 0.0) std::cout << "error 76\n";
   if (s000000 * S010000 != 0.0) std::cout << "error 77\n";
   if (s000000 * S100000 != 0.0) std::cout << "error 78\n";

   // check inner products between BasisStates and States
   if (S000000 * s000000 != 3.14) std::cout << "error 79\n";
   if (S000001 * s000001 != 3.14) std::cout << "error 80\n";
   if (S000010 * s000010 != 3.14) std::cout << "error 81\n";
   if (S000100 * s000100 != 3.14) std::cout << "error 82\n";
   if (S001000 * s001000 != 3.14) std::cout << "error 83\n";
   if (S010000 * s010000 != 3.14) std::cout << "error 84\n";
   if (S100000 * s100000 != 3.14) std::cout << "error 85\n";
   if (S000000 * s000001 != 0.0) std::cout << "error 86\n";
   if (S000000 * s000010 != 0.0) std::cout << "error 87\n";
   if (S000000 * s000100 != 0.0) std::cout << "error 88\n";
   if (S000000 * s001000 != 0.0) std::cout << "error 89\n";
   if (S000000 * s010000 != 0.0) std::cout << "error 90\n";
   if (S000000 * s100000 != 0.0) std::cout << "error 91\n";

   // check scalar products
   if ((3.14*a) * S000000 != 9.8596) std::cout << "error 54\n";
   if ((a*3.14) * S000000 != 9.8596) std::cout << "error 55\n";
   if ((a/3.14) * S000000 != 1.0) std::cout << "error 56\n";

   // check superpositions
   State<DecoupledBasis> sup1 = a + a;
   State<DecoupledBasis> sup2 = a + S000000;
   State<DecoupledBasis> sup3 = a + S000001;
   if (sup1 * a != 2.0) std::cout << "error 57\n";
   if (sup1 * S000001 != 0.0) std::cout << "error 58\n";
   if ( std::abs(sup2*a-4.14) > epsilon ) std::cout << "error 59\n";
   if ( std::abs(sup3*a-1.0) > epsilon ) std::cout << "error 60\n";

   // check that superposition works on const States
   const State<DecoupledBasis> ca {a};
   const State<DecoupledBasis> cb {a+a};
   if (ca * a != 1.0) std::cout << "error 66\n";
   if (cb * a != 2.0) std::cout << "error 67\n";

   // test compound assignment
   sup1 += a;
   if (sup1 * a != 3.0) std::cout << "error 61\n";
   sup1 -= a;
   if (sup1 * a != 2.0) std::cout << "error 62\n";
   sup1 -= a;
   sup1 *= 2.71828;
   if (sup1 * a != 2.71828) std::cout << "error 63\n";
   sup1 += S000100;
   if (sup1 * a != 2.71828) std::cout << "error 64\n";
   sup1 /= 2.71828;
   if (sup1 * a != 1.0) std::cout << "error 65\n";
}
