#include <iostream>
#include <vector>
#include <string>
#include <cmath>
#include <Eigen/Dense>
#include "../bases/DecoupledBasis.h"
#include "../operators/TlF_operators.h"

using Eigen::MatrixXcd;
using Eigen::SelfAdjointEigenSolver;
typedef std::complex<double> complex;

const double Jmax = 6;

// find matrix elements given an operator and a vector of basis states
MatrixXcd HMatElems( State<DecoupledBasis> (*H)(const DecoupledBasis&), std::vector<DecoupledBasis> QN)
{
   MatrixXcd result(QN.size(), QN.size());
   for (size_t i = 0; i<QN.size(); ++i)
      for (size_t j = 0; j<QN.size(); ++j)
         result(i, j) = QN[i] * H(QN[j]);
   return result;
}

std::vector<double> linspace(const double a, const double b, const double N)
{
   std::vector<double> result;
   double x = 0;
   for (int i=0; i<N; ++i) {
      x += std::abs(a-b)/N;
      result.push_back(x);
   }
   return result;
}

std::string csv(const auto& v)
{
   std::string result;
   for (int i=0; i<v.size(); ++i) {
      result += std::to_string( v.data()[i] );
      if (i != v.size()-1)
         result += ",";
   }
   return result;
}

int main()
{
   // write basis as vector of DecoupledBasis components:
   std::vector<DecoupledBasis> QN;
   for (double J = 0; J <= Jmax; ++J)
      for (double mJ = -J; mJ <= J; ++mJ)
         for (double m1 = -I_Tl; m1 <= I_Tl; ++m1)
               for (double m2 = -I_F; m2 <= I_F; ++m2)
                  QN.push_back(DecoupledBasis(J,mJ,I_Tl,m1,I_F,m2));

   // find matrix elements for field-free & Stark & Zeeman Hamiltonians
   MatrixXcd Hff_m { HMatElems(Hff, QN) };
   MatrixXcd HSx_m { HMatElems(HSx, QN) };
   MatrixXcd HSy_m { HMatElems(HSy, QN) };
   MatrixXcd HSz_m { HMatElems(HSz, QN) };
   MatrixXcd HZx_m { HMatElems(HZx, QN) };
   MatrixXcd HZy_m { HMatElems(HZy, QN) };
   MatrixXcd HZz_m { HMatElems(HZz, QN) };

   // find energies as a function of fields
   for ( auto Ex : linspace(0,70,100) ) {
      SelfAdjointEigenSolver<MatrixXcd> eigensolver( Hff_m + Ex*HSx_m + 18.4*HZx_m );
      std::cout << csv( eigensolver.eigenvalues() ) << std::endl;
   }
}
