#include <iostream>
#include <vector>
#include "operators/TlF_operators.h"

int main()
{
   const double Jmax = 6;

   std::vector<double> QN;
   for (double J = 0; J <= Jmax; ++J)
      for (double mJ = -J; mJ <= J; ++mJ)
         for (double m1 = -I_Tl; m1 <= I_Tl; ++m1)
               for (double m2 = -I_F; m2 <= I_F; ++m2)
                  QN.push_back(0);
   std::cout << QN.size();
}
