#ifndef STATE_H
#define STATE_H

#include <unordered_map>
#include <complex>
#include "BasisState.h"
#include "Hash.h"

typedef std::complex<double> complex;

template<typename B>
class State {
   public:
      // constructors
      State()                       : data(std::unordered_map<B,complex,BasisState_hash>{}) { }
      State(B ket, complex amp=1.0) : data(std::unordered_map<B,complex,BasisState_hash> {{ket,amp}}) { }

      // compound assignment
      State<B> operator+=(const State<B>& other)
      {
         for (const auto & [ket, amp] : other)
            (this->data)[ket] += amp;
         return *this;
      }
      State<B> operator-=(const State<B>& other) { return *this += (-1)*other; }
      State<B> operator*=(complex a)
      {
         for (const auto ket_amp : this->data)
            (this->data)[ket_amp.first] *= a;
         return *this;
      }
      State<B> operator/=(complex a) { return *this *= (1.0/a); }

      // comparison
      friend bool operator==(const State& lhs, const State& rhs) { return lhs.data == rhs.data; }
      friend bool operator!=(const State& lhs, const State& rhs) { return lhs != rhs; }

      // inner product
      friend complex operator*(const State& lhs, const State& rhs)
      {
         complex result = 0;

         for (const auto & [ket1, amp1] : lhs)
            for (const auto & [ket2, amp2] : rhs)
               if (ket1 == ket2)
                  result += amp1 * amp2;

         return result;
      }

      // scalar multiplication
      friend State operator*(complex a, State phi) { return phi *= a; } 
      friend State operator*(const State& phi, complex a) { return a * phi; } 
      friend State operator/(const State& phi, complex a) { return (1.0/a) * phi; }

      // superposition
      friend State operator+(State lhs, const State& rhs) { return lhs += rhs; } 
      friend State operator-(State lhs, const State& rhs) { return lhs -= rhs; }

      // negation
      friend State operator-(const State& psi) { return (-1.0) * psi; }

      // iterator functions
      typename std::unordered_map<B,complex,BasisState_hash>::const_iterator begin() const
      {
         return this->data.begin();
      }
      typename std::unordered_map<B,complex,BasisState_hash>::const_iterator end() const
      {
         return this->data.end();
      }

   private:
      std::unordered_map<B,complex,BasisState_hash> data;
};

#endif
