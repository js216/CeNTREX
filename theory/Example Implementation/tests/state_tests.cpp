#include <iostream>
#include <complex>
#include <limits>
#include "../states/State.h"
#include "../states/BasisState.h"
#include "../states/DecoupledBasis.h"

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

   // check comparisons
   if (s000000 == s000001) std::cout << "error";
   if (s000000 == s000010) std::cout << "error";
   if (s000000 == s000100) std::cout << "error";
   if (s000000 == s001000) std::cout << "error";
   if (s000000 == s010000) std::cout << "error";
   if (s000000 == s100000) std::cout << "error";
   if (s000001 != s000001) std::cout << "error";
   if (s000010 != s000010) std::cout << "error";
   if (s000100 != s000100) std::cout << "error";
   if (s001000 != s001000) std::cout << "error";
   if (s010000 != s010000) std::cout << "error";
   if (s100000 != s100000) std::cout << "error";

   // check inner products
   if (s000000 * s000000 != 1.0) std::cout << "error";
   if (s000001 * s000001 != 1.0) std::cout << "error";
   if (s000010 * s000010 != 1.0) std::cout << "error";
   if (s000100 * s000100 != 1.0) std::cout << "error";
   if (s001000 * s001000 != 1.0) std::cout << "error";
   if (s010000 * s010000 != 1.0) std::cout << "error";
   if (s100000 * s100000 != 1.0) std::cout << "error";
   if (s000000 * s000001 != 0.0) std::cout << "error";
   if (s000000 * s000010 != 0.0) std::cout << "error";
   if (s000000 * s000100 != 0.0) std::cout << "error";
   if (s000000 * s001000 != 0.0) std::cout << "error";
   if (s000000 * s010000 != 0.0) std::cout << "error";
   if (s000000 * s100000 != 0.0) std::cout << "error";

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
   if (S000000 == S000001) std::cout << "error";
   if (S000000 == S000010) std::cout << "error";
   if (S000000 == S000100) std::cout << "error";
   if (S000000 == S001000) std::cout << "error";
   if (S000000 == S010000) std::cout << "error";
   if (S000000 == S100000) std::cout << "error";
   if (S000001 != S000001) std::cout << "error";
   if (S000010 != S000010) std::cout << "error";
   if (S000100 != S000100) std::cout << "error";
   if (S001000 != S001000) std::cout << "error";
   if (S010000 != S010000) std::cout << "error";
   if (S100000 != S100000) std::cout << "error";

   // check inner products
   if (S000000 * S000000 != 9.8596) std::cout << "error";
   if (S000001 * S000001 != 9.8596) std::cout << "error";
   if (S000010 * S000010 != 9.8596) std::cout << "error";
   if (S000100 * S000100 != 9.8596) std::cout << "error";
   if (S001000 * S001000 != 9.8596) std::cout << "error";
   if (S010000 * S010000 != 9.8596) std::cout << "error";
   if (S100000 * S100000 != 9.8596) std::cout << "error";
   if (empty * empty != 0.0) std::cout << "error";
   if (empty * S000000 != 0.0) std::cout << "error";
   if (S000000 * S000001 != 0.0) std::cout << "error";
   if (S000000 * S000010 != 0.0) std::cout << "error";
   if (S000000 * S000100 != 0.0) std::cout << "error";
   if (S000000 * S001000 != 0.0) std::cout << "error";
   if (S000000 * S010000 != 0.0) std::cout << "error";
   if (S000000 * S100000 != 0.0) std::cout << "error";
   if (a * S000000 != 3.14) std::cout << "error";

   // check scalar products
   if ((3.14*a) * S000000 != 9.8596) std::cout << "error";
   if ((a*3.14) * S000000 != 9.8596) std::cout << "error";
   if ((a/3.14) * S000000 != 1.0) std::cout << "error";

   // check superpositions
   State<DecoupledBasis> sup1 = a + a;
   State<DecoupledBasis> sup2 = a + S000000;
   State<DecoupledBasis> sup3 = a + S000001;
   if (sup1 * a != 2.0) std::cout << "error";
   if (sup1 * S000001 != 0.0) std::cout << "error";
   if ( std::abs(sup2*a-4.14) > epsilon ) std::cout << "error";
   if ( std::abs(sup3*a-1.0) > epsilon ) std::cout << "error";
}
