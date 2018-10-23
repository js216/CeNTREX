#ifndef DECOUPLEDBASIS_H
#define DECOUPLEDBASIS_H

#include "../states/BasisState.h"

class DecoupledBasis : public BasisState {
   public:
      // constructor
      DecoupledBasis(double J, double mJ, double I1, double m1, double I2, double m2)
         : BasisState( std::unordered_map<std::string, double>(
                  { {"J", J}, {"mJ", mJ}, {"I1", I1}, {"m1", m1}, {"I2", I2}, {"m2", m2} }
                  )
               )
         { }

      // access functions
      double J() const { return this->data.at("J"); }
      double mJ() const { return this->data.at("mJ"); }
      double I1() const { return this->data.at("I1"); }
      double m1() const { return this->data.at("m1"); }
      double I2() const { return this->data.at("I2"); }
      double m2() const { return this->data.at("m2"); }
};

#endif
