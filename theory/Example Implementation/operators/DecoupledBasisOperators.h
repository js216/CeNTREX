#ifndef DECOUPLEDBASISOPERATORS_H
#define DECOUPLEDBASISOPERATORS_H

#include "../states/BasisState.h"
#include "../states/State.h"
#include "../bases/DecoupledBasis.h"

const State<DecoupledBasis> J2(const State<DecoupledBasis>& psi)
{
   State<DecoupledBasis> result = State<DecoupledBasis>();

   for (const auto & [ket, amp] : psi.data) {.
      result += State(ket, ket.J()*(ket.J()+1)*amp);
   }

   return result;
}

#endif
