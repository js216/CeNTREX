#ifndef TLF_OPERATORS_H
#define TLF_OPERATORS_H

#include <complex>
#include "DecoupledBasisOperators.h"

using namespace std::complex_literals;

// constants for TlF
const double I_Tl  = 0.5;
const double I_F   = 0.5;
const double Brot  = 6689920000;
const double c1    = 126030.0;
const double c2    = 17890.0;
const double c3    = 700.0;
const double c4    = -13300.0;
const double D_TlF = 4.2282 * 0.393430307 *5.291772e-9/4.135667e-15;
const double mu_J  = 35.0;
const double mu_Tl = 1240.5;
const double mu_F  = 2003.63;

// see Ugliness Itself at the end of DecoupledBasisOperators.h
State<DecoupledBasis> Hrot(const State<DecoupledBasis>&);
State<DecoupledBasis>  Hc1(const State<DecoupledBasis>&);
State<DecoupledBasis>  Hc2(const State<DecoupledBasis>&);
State<DecoupledBasis>  Hc4(const State<DecoupledBasis>&);
State<DecoupledBasis> Hc3a(const State<DecoupledBasis>&);
State<DecoupledBasis> Hc3b(const State<DecoupledBasis>&);
State<DecoupledBasis> Hc3c(const State<DecoupledBasis>&);
State<DecoupledBasis>  Hff(const State<DecoupledBasis>&);
State<DecoupledBasis>  HZx(const State<DecoupledBasis>&);
State<DecoupledBasis>  HZy(const State<DecoupledBasis>&);
State<DecoupledBasis>  HZz(const State<DecoupledBasis>&);
State<DecoupledBasis>  HSx(const State<DecoupledBasis>&);
State<DecoupledBasis>  HSy(const State<DecoupledBasis>&);
State<DecoupledBasis>  HSz(const State<DecoupledBasis>&);

/*
 * ROTATIONAL TERM
 */

State<DecoupledBasis> Hrot(const DecoupledBasis& psi)
{
   return Brot * J2(psi);
}

/*
 * FIELD-FREE TERMS FROM RAMSEY (1984)
 */

State<DecoupledBasis> Hc1(const DecoupledBasis& psi)
{
   return c1 * ( I1z(Jz(psi)) + .5*(I1p(Jm(psi))+I1m(Jp(psi))) );
}

State<DecoupledBasis> Hc2(const DecoupledBasis& psi)
{
   return c2 * ( I2z(Jz(psi)) + .5*(I2p(Jm(psi))+I2m(Jp(psi))) );
}

State<DecoupledBasis> Hc4(const DecoupledBasis& psi)
{
   return c4 * ( I1z(I2z(psi)) + .5*(I1p(I2m(psi))+I1m(I2p(psi))) );
}

State<DecoupledBasis> Hc3a(const DecoupledBasis& psi)
{
   return 15*c3/c1/c2 * Hc1(Hc2(psi)) / ((2*psi.J()+3)*(2*psi.J()-1));
}

State<DecoupledBasis> Hc3b(const DecoupledBasis& psi)
{
   return 15*c3/c1/c2 * Hc2(Hc1(psi)) / ((2*psi.J()+3)*(2*psi.J()-1));
}

State<DecoupledBasis> Hc3c(const DecoupledBasis& psi)
{
   return -10*c3/c4/Brot * Hc4(Hrot(psi)) / ((2*psi.J()+3)*(2*psi.J()-1));
}

State<DecoupledBasis> Hff(const DecoupledBasis& psi)
{
   return Hrot(psi) + Hc1(psi) + Hc2(psi) + Hc3a(psi) + Hc3b(psi) + Hc3c(psi) + Hc4(psi);
}

/*
 * ZEEMAN HAMILTONIAN
 */

State<DecoupledBasis> HZx(const DecoupledBasis& psi)
{
   if (psi.J() != 0) {
      return -mu_J/psi.J()*Jx(psi) - mu_Tl/psi.I1()*I1x(psi) - mu_F/psi.I2()*I2x(psi);
   }
   else
      return -mu_Tl/psi.I1()*I1x(psi) - mu_F/psi.I2()*I2x(psi);
}

State<DecoupledBasis> HZy(const DecoupledBasis& psi)
{
   if (psi.J() != 0)
      return -mu_J/psi.J()*Jy(psi) - mu_Tl/psi.I1()*I1y(psi) - mu_F/psi.I2()*I2y(psi);
   else
      return -mu_Tl/psi.I1()*I1y(psi) - mu_F/psi.I2()*I2y(psi);
}

State<DecoupledBasis> HZz(const DecoupledBasis& psi)
{
   if (psi.J() != 0)
      return -mu_J/psi.J()*Jz(psi) - mu_Tl/psi.I1()*I1z(psi) - mu_F/psi.I2()*I2z(psi);
   else
      return -mu_Tl/psi.I1()*I1z(psi) - mu_F/psi.I2()*I2z(psi);
}

/*
 * STARK HAMILTONIAN
 */

State<DecoupledBasis> HSx(const DecoupledBasis& psi)
{
   return -D_TlF * ( R1m(psi) - R1p(psi) );
}

State<DecoupledBasis> HSy(const DecoupledBasis& psi)
{
   return -D_TlF * 1i * ( R1m(psi) + R1p(psi) );
}

State<DecoupledBasis> HSz(const DecoupledBasis& psi)
{
   return -D_TlF * sqrt(2)*R10(psi);
}

// see Ugliness Itself at the end of DecoupledBasisOperators.h
State<DecoupledBasis> Hrot(const State<DecoupledBasis>& psi) {return op(Hrot, psi);}
State<DecoupledBasis>  Hc1(const State<DecoupledBasis>& psi) {return op( Hc1, psi);}
State<DecoupledBasis>  Hc2(const State<DecoupledBasis>& psi) {return op( Hc2, psi);}
State<DecoupledBasis>  Hc4(const State<DecoupledBasis>& psi) {return op( Hc4, psi);}
State<DecoupledBasis> Hc3a(const State<DecoupledBasis>& psi) {return op(Hc3a, psi);}
State<DecoupledBasis> Hc3b(const State<DecoupledBasis>& psi) {return op(Hc3b, psi);}
State<DecoupledBasis> Hc3c(const State<DecoupledBasis>& psi) {return op(Hc3c, psi);}
State<DecoupledBasis>  Hff(const State<DecoupledBasis>& psi) {return op( Hff, psi);}
State<DecoupledBasis>  HZx(const State<DecoupledBasis>& psi) {return op( HZx, psi);}
State<DecoupledBasis>  HZy(const State<DecoupledBasis>& psi) {return op( HZy, psi);}
State<DecoupledBasis>  HZz(const State<DecoupledBasis>& psi) {return op( HZz, psi);}
State<DecoupledBasis>  HSx(const State<DecoupledBasis>& psi) {return op( HSx, psi);}
State<DecoupledBasis>  HSy(const State<DecoupledBasis>& psi) {return op( HSy, psi);}
State<DecoupledBasis>  HSz(const State<DecoupledBasis>& psi) {return op( HSz, psi);}

#endif
