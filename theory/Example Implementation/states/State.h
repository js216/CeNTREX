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
         for (const auto & [ket, amp] : other.data)
            (this->data)[ket] += amp;
         return *this;
      }
      State<B> operator-=(const State<B>& other)
      {
         for (const auto & [ket, amp] : other.data)
            (this->data)[ket] -= amp;
         return *this;
      }
      State<B> operator*=(complex a)
      {
         for (const auto ket_amp : this->data)
            (this->data)[ket_amp.first] *= a;
         return *this;
      }
      State<B> operator/=(complex a)
      {
         for (const auto & ket_amp : this->data)
            (this->data)[ket_amp.first] /= a;
         return *this;
      }

      template<typename B2> friend const bool operator==(const State<B2>&, const State<B2>&);
      std::unordered_map<B,complex,BasisState_hash> data;
};

/*
 * COMPARISON
 */

template<typename B> const bool operator==(const State<B>& lhs, const State<B> rhs)
{ 
   return lhs.data == rhs.data;
}

template<typename B> const bool operator!=(const State<B>& lhs, const State<B> rhs)
{ 
   return !(lhs == rhs);
}


/*
 * INNER PRODUCT
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

/*
 * SCALAR PRODUCTS
 */

template<typename B> State<B> operator*(complex a, const State<B>& phi)
{
   State<B> result = State<B>();

   for (auto ket_amp : phi.data)
      result += State<B>(ket_amp.first, a * ket_amp.second);

   return result;
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

template<typename B> State<B> operator+(const State<B>& lhs, const State<B>& rhs)
{
   State<B> result = State<B>();

   for (const auto & [ket1, amp1] : lhs.data)
      for (const auto & [ket2, amp2] : rhs.data)
         if (ket1 == ket2)
            result += State(ket1, amp1 + amp2);

   return result;
}

template<typename B> State<B> operator-(const State<B>& lhs, const State<B>& rhs)
{
   return lhs + (-1)*lhs;
}

/*
 * NEGATION
 */

template<typename B> const State<B> operator-(const State<B>& psi)
{
   return (-1) * psi;
}

#endif
