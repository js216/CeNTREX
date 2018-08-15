#include "states/State.h"
#include "states/BasisState.h"
#include "states/DecoupledBasis.h"

int main()
{
   DecoupledBasis b {1,2,3,4,5,6};
   State<DecoupledBasis> s {b,3.45};
   s-=s;
}
