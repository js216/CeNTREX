#ifndef DECOUPLEDBASISOPERATORS_H
#define DECOUPLEDBASISOPERATORS_H

#include <cmath>
#include <complex>
#include "../states/State.h"
#include "../bases/DecoupledBasis.h"

using std::sqrt;
using std::pow;
using namespace std::complex_literals;

/*
 * ANGULAR MOMENTUM IN Z
 */

State<DecoupledBasis> J2(const DecoupledBasis& ket)
{
   return ket.J()*(ket.J()+1) * ket;
}

State<DecoupledBasis> Jz(const DecoupledBasis& ket)
{
   return ket.mJ() * ket;
}

State<DecoupledBasis> I1z(const DecoupledBasis& ket)
{
   return ket.m1() * ket;
}

State<DecoupledBasis> I2z(const DecoupledBasis& ket)
{
   return ket.m2() * ket;
}

/*
 * LADDER OPERATORS
 */

State<DecoupledBasis> Jp(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.J()-psi.mJ())*(psi.J()+psi.mJ()+1));
   DecoupledBasis ket {psi.J(), psi.mJ()+1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   return State(ket, amp);
}

State<DecoupledBasis> Jm(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.J()+psi.mJ())*(psi.J()-psi.mJ()+1));
   DecoupledBasis ket {psi.J(), psi.mJ()-1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   return State(ket, amp);
}

State<DecoupledBasis> I1p(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.I1()-psi.m1())*(psi.I1()+psi.m1()+1));
   DecoupledBasis ket {psi.J(), psi.mJ(), psi.I1(), psi.m1()+1, psi.I2(), psi.m2()};
   return State(ket, amp);
}

State<DecoupledBasis> I1m(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.I1()+psi.m1())*(psi.I1()-psi.m1()+1));
   DecoupledBasis ket {psi.J(), psi.mJ(), psi.I1(), psi.m1()-1, psi.I2(), psi.m2()};
   return State(ket, amp);
}

State<DecoupledBasis> I2p(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.I2()-psi.m2())*(psi.I2()+psi.m2()+1));
   DecoupledBasis ket {psi.J(), psi.mJ(), psi.I1(), psi.m1(), psi.I2(), psi.m2()+1};
   return State(ket, amp);
}

State<DecoupledBasis> I2m(const DecoupledBasis& psi)
{
   double amp = sqrt((psi.I2()+psi.m2())*(psi.I2()-psi.m2()+1));
   DecoupledBasis ket {psi.J(), psi.mJ(), psi.I1(), psi.m1(), psi.I2(), psi.m2()-1};
   return State(ket, amp);
}

/*
 * ANGULAR MOMENTUM IN X, Y
 */

State<DecoupledBasis> Jx(const DecoupledBasis& psi)
{
   return 0.5*( Jp(psi) + Jm(psi) );
}

State<DecoupledBasis> Jy(const DecoupledBasis& psi)
{
   return -0.5i*( Jp(psi) - Jm(psi) );
}

State<DecoupledBasis> I1x(const DecoupledBasis& psi)
{
   return 0.5*( I1p(psi) + I1m(psi) );
}

State<DecoupledBasis> I1y(const DecoupledBasis& psi)
{
   return -0.5i*( I1p(psi) - I1m(psi) );
}

State<DecoupledBasis> I2x(const DecoupledBasis& psi)
{
   return 0.5*( I2p(psi) + I2m(psi) );
}

State<DecoupledBasis> I2y(const DecoupledBasis& psi)
{
   return -0.5i*( I2p(psi) - I2m(psi) );
}

/*
 * TENSORS
 */

State<DecoupledBasis> R10(const DecoupledBasis& psi)
{
   double amp1 = sqrt((psi.J()-psi.mJ())*(psi.J()+psi.mJ())/(8*pow(psi.J(),2)-2));
   DecoupledBasis ket1 {psi.J()-1, psi.mJ(), psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   double amp2 = sqrt((psi.J()-psi.mJ()+1)*(psi.J()+psi.mJ()+1)/(6+8*psi.J()*(psi.J()+2)));
   DecoupledBasis ket2 {psi.J()+1, psi.mJ(), psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   return State(ket1,amp1) + State(ket2,amp2);
}

State<DecoupledBasis> R1m(const DecoupledBasis& psi)
{
   double amp1 = -0.5*sqrt((psi.J()+psi.mJ())*(psi.J()+psi.mJ()-1)/(4*pow(psi.J(),2)-1));
   DecoupledBasis ket1 {psi.J()-1, psi.mJ()-1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   double amp2 = 0.5*sqrt((psi.J()-psi.mJ()+1)*(psi.J()-psi.mJ()+2)/(3+4*psi.J()*(psi.J()+2)));
   DecoupledBasis ket2 {psi.J()+1, psi.mJ()-1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   return State(ket1,amp1) + State(ket2,amp2);
}

State<DecoupledBasis> R1p(const DecoupledBasis& psi)
{
   double amp1 = -0.5*sqrt((psi.J()-psi.mJ())*(psi.J()-psi.mJ()-1)/(4*pow(psi.J(),2)-1));
   DecoupledBasis ket1 {psi.J()-1, psi.mJ()+1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   double amp2 = 0.5*sqrt((psi.J()+psi.mJ()+1)*(psi.J()+psi.mJ()+2)/(3+4*psi.J()*(psi.J()+2)));
   DecoupledBasis ket2 {psi.J()+1, psi.mJ()+1, psi.I1(), psi.m1(), psi.I2(), psi.m2()};
   return State(ket1,amp1) + State(ket2,amp2);
}

/*
 * UGLINESS ITSELF: BJARNE, SORRY
 * (code to overload the above functions to accept a State<>& input, not just DecoupledBasis&)
 * (there has to be some prettier way to do this!)
 */

State<DecoupledBasis> op( State<DecoupledBasis> (*f)(const DecoupledBasis&), const State<DecoupledBasis>& psi )
{
   State<DecoupledBasis> result;
   for (const auto & [ket, amp] : psi)
      result += amp * (*f)(ket);
   return result;
}

State<DecoupledBasis>  J2(const State<DecoupledBasis>& psi) {return op( J2, psi);}
State<DecoupledBasis>  Jz(const State<DecoupledBasis>& psi) {return op( Jz, psi);}
State<DecoupledBasis> I1z(const State<DecoupledBasis>& psi) {return op(I1z, psi);}
State<DecoupledBasis> I2z(const State<DecoupledBasis>& psi) {return op(I2z, psi);}
State<DecoupledBasis>  Jp(const State<DecoupledBasis>& psi) {return op( Jp, psi);}
State<DecoupledBasis>  Jm(const State<DecoupledBasis>& psi) {return op( Jm, psi);}
State<DecoupledBasis> I1p(const State<DecoupledBasis>& psi) {return op(I1p, psi);}
State<DecoupledBasis> I1m(const State<DecoupledBasis>& psi) {return op(I1m, psi);}
State<DecoupledBasis> I2p(const State<DecoupledBasis>& psi) {return op(I2p, psi);}
State<DecoupledBasis> I2m(const State<DecoupledBasis>& psi) {return op(I2m, psi);}
State<DecoupledBasis>  Jx(const State<DecoupledBasis>& psi) {return op( Jx, psi);}
State<DecoupledBasis>  Jy(const State<DecoupledBasis>& psi) {return op( Jy, psi);}
State<DecoupledBasis> I1x(const State<DecoupledBasis>& psi) {return op(I1x, psi);}
State<DecoupledBasis> I1y(const State<DecoupledBasis>& psi) {return op(I1y, psi);}
State<DecoupledBasis> I2x(const State<DecoupledBasis>& psi) {return op(I2x, psi);}
State<DecoupledBasis> I2y(const State<DecoupledBasis>& psi) {return op(I2y, psi);}
State<DecoupledBasis> R10(const State<DecoupledBasis>& psi) {return op(R10, psi);}
State<DecoupledBasis> R1m(const State<DecoupledBasis>& psi) {return op(R1m, psi);}
State<DecoupledBasis> R1p(const State<DecoupledBasis>& psi) {return op(R1p, psi);}

#endif
