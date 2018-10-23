#ifndef BASISSTATE_H
#define BASISSTATE_H

#include <unordered_map>
#include <string>
#include <complex>
#include <functional>

typedef std::complex<double> complex;

class BasisState {
   public:
      // constructors
      BasisState() : data(std::unordered_map<std::string, double> {}) {}
      BasisState(std::unordered_map<std::string, double> data) :data(data) {}

   private:
      friend const bool operator==(const BasisState&, const BasisState&);
      friend class BasisState_hash;

   protected:
      std::unordered_map<std::string, double> data;
};

// comparison
const bool operator==(const BasisState& lhs, const BasisState& rhs)
{
   return lhs.data == rhs.data;
}
const bool operator!=(const BasisState& lhs, const BasisState& rhs)
{
   return !(lhs == rhs);
}

// inner product
complex operator*(const BasisState& lhs, const BasisState& rhs)
{
   if (lhs == rhs)
      return 1;
   else
      return 0;
}

#endif
