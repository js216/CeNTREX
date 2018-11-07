#include <iostream>
#include "../bases/DecoupledBasis.h"

int main()
{
   DecoupledBasis b {1,2,3,4,5,6};
   if ( b.J() != 1.0) std::cout << "error";
   if (b.mJ() != 2.0) std::cout << "error";
   if (b.I1() != 3.0) std::cout << "error";
   if (b.m1() != 4.0) std::cout << "error";
   if (b.I2() != 5.0) std::cout << "error";
   if (b.m2() != 6.0) std::cout << "error";
}
