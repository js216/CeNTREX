#ifndef DECOUPLEDBASIS_H
#define DECOUPLEDBASIS_H

#include "BasisState.h"

class DecoupledBasis : public BasisState {
   public:
      // constructor
      DecoupledBasis(double J, double mJ, double I1, double m1, double I2, double m2)
         : BasisState( std::unordered_map<std::string, double>(
                  { {"J", J}, {"mJ", mJ}, {"I1", I1}, {"m1", m1}, {"I2", I2}, {"m2", m2} }
                  )
               )
         { }
};

#endif
