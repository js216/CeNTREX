#include <limits>
#include "../states/State.h"
#include "../states/BasisState.h"
#include "../bases/DecoupledBasis.h"

const double epsilon = 10 * std::numeric_limits<double>::epsilon();

int main()
{
   // create some states
   DecoupledBasis a {0.0,0,0,0,0,0};
   State<DecoupledBasis> A {a};
   State<DecoupledBasis> B = 1.5*A;

   // test inner products that require implicit conversions
   if (a*a != 1.0) return 1;
   if (A*A != 1.0) return 2;
   if (a*A != 1.0) return 3;
   if (A*a != 1.0) return 4;

   // test compound assignment
   if (B*a != 1.5) return 13;
   B += a;
   if (B*a != 2.5) return 14;
   B -= a;
   if (B*a != 1.5) return 15;
   B *= 2.0;
   if (B*a != 3.0) return 24;
   B /= 2.0;
   if (B*a != 1.5) return 25;

   // test comparisons
   if ( (a==a) == false ) return 16;
   if ( (A==A) == false ) return 17;
   if ( (a==A) == false ) return 18;
   if ( (A==a) == false ) return 19;
   if ( (A==B) == true ) return 20;
   if ( (a==B) == true ) return 21;
   if ( (B==a) == true ) return 22;

   /*
    * TESTS FROM HERE ON FAIL TO COMPILE
    */

   // test scalar multiplication that requires implicit conversions
   3.14*a;
   if ((3.14*a)*a != 1.0) return 5;
   if ((a*3.14)*a != 1.0) return 6;
   if ((a/3.14)*a != 1.0) return 7;

   // test negation
   if ((-a)*a != -1.0) return 23;

   // test superposition requiring implicit conversions
   if ((a+a)*a != 2.0) return 8;
   if ((A+a)*a != 2.0) return 9;
   if ((a+A)*a != 2.0) return 10;
   if ((B-a)*a != 0.5) return 11;
   if ((a-B)*a != -0.5) return 12;
}
