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

      template<typename B2> friend const bool operator==(const State<B2>&, const State<B2>&);
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
 * INNER PRODUCT
 */

template<typename B> complex operator*(const State<B>& lhs, const State<B>& rhs)
{
   complex result = 0;

   for (const auto & [ket1, amp1] : lhs.data)
      for (const auto & [ket2, amp2] : rhs.data)
         if (ket1 == ket2)
            result += amp1 * amp2;

   return result;
}

/*
 * SCALAR MULTIPLICATION
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

   /*
    * LHS and RHS might both contain a ket, possibly with different amplitudes;
    * in this case, the ket is considered 'common' and we just need to sum the
    * amplitudes. Else (common == false), the ket only appears in LHS, and we
    * just add it to the sum. Finally, we have to check for kets which appear in
    * RHS only. There has to be a more efficient way to do this, but this seems
    * to work well enough for my purposes.
    * */

   // check for kets that are in both LHS and RHS, or in LHS only
   for (const auto & [ket1, amp1] : lhs.data) {
      bool common = false;
      for (const auto & [ket2, amp2] : rhs.data)
         if (ket1 == ket2) {
            common = true;
            result += State(ket1, amp1 + amp2);
         }
      if (common == false)
         result += State(ket1, amp1);
   }

   // check for kets that are in RHS only
   for (const auto & [ket1, amp1] : rhs.data) {
      bool common = false;
      for (const auto & [ket2, amp2] : lhs.data)
         if (ket1 == ket2)
            common = true;
      if (common == false)
         result += State(ket1, amp1);
   }

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
