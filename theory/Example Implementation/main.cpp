#include "states/State.h"
#include "states/BasisState.h"
#include "bases/DecoupledBasis.h"
#include "operators/DecoupledBasisOperators.h"

int main()
{
   DecoupledBasis b {1,2,3,4,5,6};
   State<DecoupledBasis> s {b,3.45};
   State<DecoupledBasis> result = J2(s);
}
