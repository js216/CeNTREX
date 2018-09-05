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
      State()                            : data(std::unordered_map<B,complex,BasisState_hash>{}) { }
      State(B ket, complex amp)          : data(std::unordered_map<B,complex,BasisState_hash> {{ket,amp}}) { }
      State(std::pair<B,complex> data)   : data(std::unordered_map<B,complex,BasisState_hash> {data}) { } 
      State(std::unordered_map<B,complex,BasisState_hash>& data) : data(data) { } 

      // compound assignment
      State<B> operator+=(const State<B>& other)
      {
         for (const auto & [ket, amp] : other)
            (this->data)[ket] += amp;
         return *this;
      }
      State<B> operator-=(const State<B>& other)
      {
         return *this += (-1)*other;
      }
      State<B> operator*=(complex a)
      {
         for (const auto ket_amp : this->data)
            (this->data)[ket_amp.first] *= a;
         return *this;
      }
      State<B> operator/=(complex a)
      {
         return *this *= (1.0/a);
      }

      // comparison
      template<typename B2> friend const bool operator==(const State<B2>&, const State<B2>&);

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

/*
 * COMPARISON
 */

template<typename B> const bool operator==(const State<B>& lhs, const State<B>& rhs)
{ 
   return lhs.data == rhs.data;
}

template<typename B> const bool operator!=(const State<B>& lhs, const State<B>& rhs)
{ 
   return !(lhs == rhs);
}


/*
 * INNER PRODUCTS
 */

template<typename B> complex operator*(const State<B>& lhs, const State<B>& rhs)
{
   complex result = 0;

   for (const auto & [ket1, amp1] : lhs)
      for (const auto & [ket2, amp2] : rhs)
         if (ket1 == ket2)
            result += amp1 * amp2;

   return result;
}

template<typename B> complex operator*(const State<B>& lhs, const B& rhs)
{
   return lhs * State(rhs, 1.0);
}

template<typename B> complex operator*(const B& lhs, const State<B>& rhs)
{
   return State(lhs, 1.0) * rhs;
}


/*
 * SCALAR MULTIPLICATION
 */

template<typename B> State<B> operator*(complex a, State<B> phi)
{
   return phi *= a;
}

template<typename B> State<B> operator*(const State<B>& phi, complex a)
{
   return a * phi;
}

template<typename B> State<B> operator/(const State<B>& phi, complex a)
{
   return (1.0/a) * phi;
}

/*
 * SUPERPOSITION
 */

template<typename B> State<B> operator+(State<B> lhs, const State<B>& rhs)
{
   return lhs += rhs;
}

template<typename B> State<B> operator-(State<B> lhs, const State<B>& rhs)
{
   return lhs -= lhs;
}

/*
 * NEGATION
 */

template<typename B> const State<B> operator-(const State<B>& psi)
{
   return (-1) * psi;
}

#endif
