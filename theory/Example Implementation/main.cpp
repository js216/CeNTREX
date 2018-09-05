#include <iostream>
#include "states/State.h"
#include "states/BasisState.h"
#include "bases/DecoupledBasis.h"
#include "operators/DecoupledBasisOperators.h"

int main()
{
   DecoupledBasis b {1,2,3,4,5,6};
   DecoupledBasis b2 {1,2,9,4,5,6};
   State<DecoupledBasis> s {b,3.45};
   State<DecoupledBasis> s2 {b2,1.93};

   for (const auto & [ket, amp] : s+s2)
      std::cout << amp << std::endl;

   //State<DecoupledBasis> result = J2(s);
}
