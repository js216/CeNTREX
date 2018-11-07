#include <iostream>
#include <limits>
#include <vector>
#include <cmath>
#include "../operators/DecoupledBasisOperators.h"
#include "../operators/TlF_operators.h"

const double epsilon = 10 * std::numeric_limits<double>::epsilon();

int main()
{
   const double Jmax = 6.0;

   // write basis as vector of DecoupledBasis components:
   std::vector<DecoupledBasis> QN;
   for (double J = 0; J <= Jmax; ++J)
      for (double mJ = -J; mJ <= J; ++mJ)
         for (double m1 = -I_Tl; m1 <= I_Tl; ++m1)
               for (double m2 = -I_F; m2 <= I_F; ++m2)
                  QN.push_back(DecoupledBasis(J,mJ,I_Tl,m1,I_F,m2));

   // test Hrot
   for (size_t i = 0; i<QN.size(); ++i)
      for (size_t j = 0; j<QN.size(); ++j)
         if (i != j)
            if (std::abs(QN[i]*Hrot(QN[j])) != 0)
               return 1;
   for (double J = 0; J <= Jmax; ++J) {
      auto a = DecoupledBasis(J,0,0,0,0,0);
      if (std::abs(a*Hrot(a))/Brot != J*(J+1))
         return 2;
   }

   // test Jp and Jm
   for (size_t i = 0; i<QN.size(); ++i)
      for (size_t j = 0; j<QN.size(); ++j) {
         auto a = QN[i];
         auto b = QN[j];
         if (a.mJ() == b.mJ()) {
            if (std::abs(a*Jp(b))/Brot != 0.0)
               return 3;
            if (std::abs(a*Jm(b))/Brot != 0.0)
               return 6;
         }
         if ((a.mJ() == b.mJ()+1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2()))
            if (std::abs(a*Jp(b))/Brot < epsilon)
               return 4;
         if ((a.mJ() == b.mJ()-1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2()))
            if (std::abs(a*Jm(b))/Brot < epsilon)
               return 5;
      }

   // test Jx
   for (size_t i = 0; i<QN.size(); ++i)
      for (size_t j = 0; j<QN.size(); ++j) {
         auto a = QN[i];
         auto b = QN[j];
         if (a.mJ() == b.mJ())
            if (std::abs(a*Jx(b)) != 0.0)
               return 7;
         if ((a.mJ() == b.mJ()+1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2()))
            if (std::abs(a*Jx(b))/Brot < epsilon)
               return 8;
         if ((a.mJ() == b.mJ()-1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2()))
            if (std::abs(a*Jx(b))/Brot < epsilon)
               return 9;
      }

   /*
   // define states
   DecoupledBasis a {1,-1,0.5,-0.5,0.5,-0.5};
   DecoupledBasis b {1,0,0.5,-0.5,0.5,-0.5};
   auto c = Jm(b) - State(DecoupledBasis(1,-1,0.5,-0.5,0.5,-0.5), 1.0);
   // print out quantum numbers
   std::cout << a.J() << a.mJ() << a.m1() << a.m2() << std::endl;
   std::cout << b.J() << b.mJ() << b.m1() << b.m2() << std::endl;
   for (const auto & [ket, amp] : c) {
      std::cout << amp << std::endl;
      std::cout << ket.J() << ket.mJ() << ket.m1() << ket.m2() << std::endl;
   }
   // check inner product
   if (std::abs(a*c) < epsilon) {
      return 15;
   }
   */

   // test HZx
   for (size_t i = 0; i<QN.size(); ++i)
      for (size_t j = 0; j<QN.size(); ++j) {
         auto a = QN[i];
         auto b = QN[j];
         if (a.mJ() == b.mJ())
            if (std::abs(a*Jx(b)) != 0.0)
               return 10;
         if ((a.mJ() == b.mJ()+1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2()))
            if (std::abs(a*HZx(b))/Brot < epsilon)
               return 11;
         if ((a.mJ() == b.mJ()-1) && (a.J() == b.J()) && (a.m1() == b.m1()) && (a.m2() == b.m2())) {
            if (a.J() != 0.0) {
               if (std::abs(a*HZx(b)) < epsilon) {
                  std::cout << a.J() << a.mJ() << a.m1() << a.m2() << std::endl;
                  std::cout << b.J() << b.mJ() << b.m1() << b.m2() << std::endl;
                  for (const auto & [ket, amp] : HZx(b)) {
                     std::cout << amp << std::endl;
                     std::cout << ket.J() << ket.mJ() << ket.m1() << ket.m2() << std::endl;
                  }
                  return 12;
               }
            } else {
               return 13;
            }
         }
      }
}
